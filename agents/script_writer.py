"""
Script Writer Agent: generates N distinct ad scripts from the research brief.
Each script follows direct-response ad structure and is tagged with
broll_cues for the video editor to use for B-roll placement.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

import config
from utils.logger import logger


@dataclass
class AdScript:
    """A single ad script with metadata."""
    number: int
    ad_type: str          # "full_broll" or "talking_head"
    angle: str            # e.g., "tax savings hook"
    script_text: str      # The spoken text for the avatar
    broll_cues: list[dict] = field(default_factory=list)
    # [{"query": str, "at_word": str, "duration_hint": float}]
    estimated_duration_seconds: int = 45


AD_STRUCTURE_GUIDE = """
A great 30-50 second Facebook ad script follows this exact structure:

1. HOOK (0-4 seconds): A bold, pattern-interrupting opening statement or question
   that immediately grabs attention. Must be specific and create curiosity or fear.

2. PROBLEM (5-15 seconds): Agitate the pain point. Make them feel it.
   Use "you" language. Be conversational, not formal.

3. SOLUTION (16-30 seconds): Introduce the offer as the solution.
   Explain the unique mechanism briefly. Build desire.

4. PROOF/CREDIBILITY (31-38 seconds): Social proof, stats, or specifics.
   One or two concrete numbers or outcomes.

5. CTA (39-50 seconds): Clear call to action. Create urgency.
   Tell them exactly what to do next.

IMPORTANT RULES:
- Write EXACTLY as the avatar will speak it — no stage directions, no brackets
- Keep sentences SHORT. One idea per sentence.
- Use contractions (don't, you're, it's)
- Avoid corporate language. Be friendly and direct.
- Total word count: 90-130 words (for ~45 second delivery at natural speaking pace)
- NO em-dashes or complex punctuation — use commas and periods only
"""


def _build_system_prompt() -> str:
    return (
        "You are a world-class direct-response copywriter specializing in Facebook video ads. "
        "You write scripts that convert viewers into leads. Your scripts are conversational, "
        "emotionally compelling, and drive action. You understand consumer psychology deeply."
    )


def _build_script_prompt(brief: dict, angle: str, ad_number: int, ad_type: str) -> str:
    return f"""
Write a Facebook video ad script for {brief.get('company_name', 'this company')}.

COMPANY RESEARCH:
- Offer: {brief.get('offer_summary', '')}
- Target audience: {brief.get('target_audience', '')}
- Pain points: {', '.join(brief.get('pain_points', []))}
- Key benefits: {', '.join(brief.get('key_benefits', []))}
- Social proof: {', '.join(brief.get('social_proof', []))}
- CTA: {brief.get('cta_suggestion', 'Learn more')}
- Unique angle for THIS ad: {angle}

AD STRUCTURE TO FOLLOW:
{AD_STRUCTURE_GUIDE}

AD TYPE: {ad_type}
- If "full_broll": Avatar is on screen the whole time with B-roll overlaid at key moments
- If "talking_head": Avatar is bottom of screen; pick moments where B-roll should show lifestyle/product scenes

Return a JSON object with EXACTLY this structure:
{{
  "angle": "{angle}",
  "script_text": "The exact spoken words for the avatar. Nothing else.",
  "estimated_duration_seconds": 45,
  "broll_cues": [
    {{
      "query": "search query for Pexels stock video that matches this moment",
      "start_second": 8,
      "end_second": 14,
      "description": "what B-roll to show here"
    }},
    {{
      "query": "another B-roll moment query",
      "start_second": 20,
      "end_second": 28,
      "description": "what B-roll to show here"
    }},
    {{
      "query": "final B-roll moment",
      "start_second": 32,
      "end_second": 40,
      "description": "closing B-roll"
    }}
  ]
}}

Return ONLY the JSON. No markdown, no explanation.
"""


async def generate_scripts(
    brief: dict,
    num_ads: int,
    ad_type: str = "full_broll",
) -> list[AdScript]:
    """
    Generates `num_ads` distinct ad scripts using different angles from the brief.
    Returns a list of AdScript objects.
    """
    angles = brief.get("ad_angle_ideas", [])

    # Pad or cycle angles if we need more than provided
    while len(angles) < num_ads:
        angles += [
            "problem-agitate-solve with emotional hook",
            "surprising statistic opener",
            "relatable story hook",
            "direct benefit opener",
            "question hook",
        ]

    claude = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    scripts = []

    for i in range(num_ads):
        angle = angles[i % len(angles)]
        logger.info(f"Writing script {i+1}/{num_ads} — angle: {angle}")

        # Alternate ad types if generating both
        current_type = ad_type

        try:
            message = claude.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1200,
                system=_build_system_prompt(),
                messages=[
                    {
                        "role": "user",
                        "content": _build_script_prompt(brief, angle, i + 1, current_type),
                    }
                ],
            )

            raw = message.content[0].text.strip()
            # Strip markdown code block if present
            raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
            data = json.loads(raw)

            script = AdScript(
                number=i + 1,
                ad_type=current_type,
                angle=data.get("angle", angle),
                script_text=data.get("script_text", "").strip(),
                broll_cues=data.get("broll_cues", []),
                estimated_duration_seconds=data.get("estimated_duration_seconds", 45),
            )
            scripts.append(script)
            logger.info(f"Script {i+1} ready ({len(script.script_text.split())} words)")

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Script {i+1} generation failed: {e}")
            # Generate a simple fallback script
            fallback = _fallback_script(brief, angle, i + 1, current_type)
            scripts.append(fallback)

    return scripts


def _fallback_script(brief: dict, angle: str, number: int, ad_type: str) -> AdScript:
    """Returns a basic fallback script if Claude generation fails."""
    company = brief.get("company_name", "our company")
    audience = brief.get("target_audience", "employees")
    benefits = brief.get("key_benefits", ["save money", "reduce stress"])[:2]
    cta = brief.get("cta_suggestion", "click the link below to learn more")

    script_text = (
        f"Did you know that most {audience} are leaving hundreds of dollars on the table every year? "
        f"The truth is, you're probably overpaying in taxes and not even realizing it. "
        f"That's exactly why {company} was created. "
        f"We help {audience} {benefits[0]} and {benefits[1] if len(benefits) > 1 else 'keep more of their paycheck'}. "
        f"And it takes less than five minutes to get started. "
        f"If you want to stop leaving money on the table, {cta}."
    )

    return AdScript(
        number=number,
        ad_type=ad_type,
        angle=angle,
        script_text=script_text,
        broll_cues=[
            {"query": "employee at work office", "start_second": 8, "end_second": 14, "description": "Office worker"},
            {"query": "person saving money piggy bank", "start_second": 20, "end_second": 27, "description": "Savings"},
            {"query": "happy family financial freedom", "start_second": 32, "end_second": 40, "description": "Happy outcome"},
        ],
        estimated_duration_seconds=45,
    )
