"""
Research Agent: scrapes the target website and searches the web
to build a rich context brief used by the script writer.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import anthropic
import httpx
from bs4 import BeautifulSoup
from tavily import TavilyClient

import config
from utils.logger import logger


async def _fetch_page(url: str) -> str:
    """Fetches and returns clean text content from a URL."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            # Remove nav, footer, scripts, styles
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            # Truncate to 6000 chars to avoid context bloat
            return text[:6000]
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return ""


def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Runs a Tavily web search and returns results."""
    try:
        client = TavilyClient(api_key=config.TAVILY_API_KEY)
        response = client.search(query, max_results=max_results, search_depth="advanced")
        return response.get("results", [])
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}")
        return []


async def research_website(website_url: str) -> dict:
    """
    Main research function. Returns a structured brief dict with:
    - company_name
    - offer_summary
    - target_audience
    - pain_points (list)
    - key_benefits (list)
    - social_proof (list)
    - cta_suggestion
    - raw_content (for script writer)
    """
    logger.info(f"Researching: {website_url}")

    # Ensure URL has scheme
    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    # 1. Scrape the website itself
    site_content = await _fetch_page(website_url)

    # 2. Additional Tavily searches
    domain = website_url.split("//")[-1].split("/")[0]
    search_tasks = [
        asyncio.get_event_loop().run_in_executor(
            None, _tavily_search, f"{domain} employee benefits services"
        ),
        asyncio.get_event_loop().run_in_executor(
            None, _tavily_search, f"{domain} reviews testimonials"
        ),
        asyncio.get_event_loop().run_in_executor(
            None, _tavily_search, f"employee benefits tax savings IRS section 125 employer"
        ),
    ]
    search_results_list = await asyncio.gather(*search_tasks)

    search_snippets = []
    for results in search_results_list:
        for r in results[:3]:
            snippet = r.get("content", "")[:500]
            if snippet:
                search_snippets.append(snippet)

    combined_context = f"""
WEBSITE CONTENT FROM {website_url}:
{site_content}

WEB SEARCH CONTEXT:
{chr(10).join(search_snippets[:10])}
"""

    # 3. Use Claude to synthesize into a structured brief
    claude = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    prompt = f"""
You are a direct-response advertising expert. Analyze the following content about a company
and extract a research brief for creating Facebook ad scripts.

CONTENT:
{combined_context}

Return ONLY a JSON object with these exact keys (no markdown, just raw JSON):
{{
  "company_name": "...",
  "offer_summary": "1-2 sentence description of what they offer",
  "target_audience": "Who this is for (e.g., 'employees at small-to-mid-size companies')",
  "pain_points": ["pain 1", "pain 2", "pain 3", "pain 4"],
  "key_benefits": ["benefit 1", "benefit 2", "benefit 3", "benefit 4"],
  "social_proof": ["proof point 1", "proof point 2"],
  "cta_suggestion": "Primary call to action (e.g., 'Schedule a free consultation')",
  "unique_mechanism": "What makes this different from competitors",
  "ad_angle_ideas": ["angle 1", "angle 2", "angle 3", "angle 4", "angle 5"]
}}
"""

    message = claude.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    import json
    try:
        brief = json.loads(message.content[0].text.strip())
    except (json.JSONDecodeError, IndexError, AttributeError):
        # Fallback brief if parsing fails
        logger.warning("Claude brief parsing failed, using fallback")
        brief = {
            "company_name": domain,
            "offer_summary": "Employee benefits and advocacy services",
            "target_audience": "Employees and HR professionals",
            "pain_points": [
                "High out-of-pocket expenses",
                "Confusing benefits options",
                "Not maximizing tax savings",
                "Lack of employer support",
            ],
            "key_benefits": [
                "Reduce taxable income",
                "Save money on healthcare",
                "Easy enrollment",
                "Expert guidance",
            ],
            "social_proof": ["Thousands of employees helped"],
            "cta_suggestion": "Learn how much you could save",
            "unique_mechanism": "IRS-approved section 125 benefit plans",
            "ad_angle_ideas": [
                "Tax savings angle",
                "Problem/solution",
                "Testimonial style",
                "Shocking statistic hook",
                "Question hook",
            ],
        }

    brief["website_url"] = website_url
    brief["raw_snippets"] = search_snippets[:5]
    logger.info(f"Research complete for {brief.get('company_name', domain)}")
    return brief
