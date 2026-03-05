"""
B-roll Agent — Claude Sonnet 4.6 call #2.
Generates hyper-specific Pexels search queries from the script, then fetches real clip URLs.
"""
from __future__ import annotations

import json
import re

import anthropic

from config.settings import settings
from models.schemas import AdScript, BrollClip
from prompts.broll_agent_prompt import BROLL_AGENT_SYSTEM_PROMPT
from services import pexels
from utils.logger import get_logger

logger = get_logger(__name__)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


async def get_broll_clips(script: AdScript) -> list[BrollClip]:
    """
    Step 1: Call Claude to generate 3–4 hyper-specific Pexels search queries.
    Step 2: Query Pexels for each and select the best matching clip.
    Step 3: Return populated BrollClip objects with real URLs.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    user_msg = (
        f'Generate B-roll queries for this USAEA ad script.\n\n'
        f'Ad Type: {script.ad_type}\n'
        f'State: {script.state}\n'
        f'Estimated duration: {script.estimated_seconds:.1f}s\n\n'
        f'[HOOK] (0–3s)\n{script.hook}\n\n'
        f'[BODY] (3–17s)\n{script.body}\n\n'
        f'[CTA] (17–{script.estimated_seconds:.0f}s)\n{script.cta}'
    )

    logger.info(f'Calling B-roll Agent for script {script.script_id}')
    response = await client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=800,
        system=BROLL_AGENT_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_msg}],
    )
    raw = response.content[0].text
    logger.info(f'B-roll Agent response: {len(raw)} chars')

    try:
        clip_specs = json.loads(_strip_json_fences(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f'B-roll Agent returned invalid JSON: {exc}\nRaw: {raw[:300]}'
        )

    # Fetch real Pexels URLs for each query
    populated: list[BrollClip] = []
    for spec in clip_specs:
        query = spec.get('search_query', '')
        placement = spec.get('placement_hint', '')
        description = spec.get('description', '')

        clip_data = await _fetch_clip(query)
        if not clip_data:
            # Try a shorter 2-word fallback query
            short_query = ' '.join(query.split()[:2])
            logger.info(f"No results for '{query}' — trying fallback '{short_query}'")
            clip_data = await _fetch_clip(short_query)

        if clip_data:
            populated.append(BrollClip(
                search_query=query,
                clip_url=clip_data['clip_url'],
                duration_seconds=clip_data['duration_seconds'],
                description=description,
                placement_hint=placement,
            ))
            logger.info(f"B-roll clip found for '{query}': {clip_data['clip_url'][:60]}...")
        else:
            logger.warning(f"No Pexels clip found for query: '{query}' — skipping")

    logger.info(
        f'B-roll Agent: {len(populated)}/{len(clip_specs)} clips found for '
        f'script {script.script_id}'
    )
    return populated


async def _fetch_clip(query: str) -> dict | None:
    """Searches Pexels and returns best clip data dict, or None."""
    results = await pexels.search_clips(query, per_page=5)
    if not results:
        return None
    return pexels.select_best_clip(results, target_duration_range=(4, 8))
