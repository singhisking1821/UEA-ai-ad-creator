"""
Timeline Agent — Claude Sonnet 4.6 call #3.
Constructs the Shotstack JSON payload from all assembled assets.
"""
from __future__ import annotations

import json
import re

import anthropic

from config.settings import settings
from models.schemas import AdScript, BrollClip, ShotstackPayload
from prompts.timeline_agent_prompt import TIMELINE_AGENT_SYSTEM_PROMPT
from utils.logger import get_logger

logger = get_logger(__name__)


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


async def build_shotstack_payload(
    script: AdScript,
    heygen_url: str,
    broll_clips: list[BrollClip],
) -> ShotstackPayload:
    """
    Assembles all asset information and calls Claude to produce the exact
    Shotstack JSON payload. Validates total_duration <= 22 seconds.
    Returns a ShotstackPayload ready to POST to Shotstack /render.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    total_duration = min(script.estimated_seconds + 3.5, float(settings.MAX_VIDEO_SECONDS))

    broll_lines = '\n'.join([
        f'  - search_query: "{c.search_query}" | URL: {c.clip_url} | '
        f'duration: {c.duration_seconds:.1f}s | placement: {c.placement_hint}'
        for c in broll_clips
    ]) or '  (no B-roll clips available)'

    user_msg = (
        f'Build a Shotstack timeline for this USAEA ad.\n\n'
        f'Script duration (talking head): {script.estimated_seconds:.1f}s\n'
        f'Total video target (incl. end screen): {total_duration:.1f}s\n\n'
        f'TRACK 1 — HeyGen Talking Head:\n'
        f'  URL: {heygen_url}\n'
        f'  start=0, length={script.estimated_seconds:.1f}, volume=1\n\n'
        f'TRACK 2 — B-roll clips (overlay only, volume=0):\n'
        f'{broll_lines}\n\n'
        f'TRACK 3 — End screen:\n'
        f'  start={script.estimated_seconds:.1f}, length=3.5\n'
        f'  Style: background #1E3A5F, "Call Now — Free Consultation", '
        f'phone placeholder\n\n'
        f'Script context for B-roll timing decisions:\n'
        f'Hook (0–3s): {script.hook}\n'
        f'Body (3–{script.estimated_seconds - 5:.0f}s): {script.body}\n'
        f'CTA (last 5s): {script.cta}'
    )

    logger.info(f'Calling Timeline Agent for script {script.script_id}')
    response = await client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=3000,
        system=TIMELINE_AGENT_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_msg}],
    )
    raw = response.content[0].text
    logger.info(f'Timeline Agent response: {len(raw)} chars')

    try:
        parsed = json.loads(_strip_json_fences(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f'Timeline Agent returned invalid JSON: {exc}\nRaw (first 400): {raw[:400]}'
        )

    timeline_json = parsed.get('timeline_json')
    track_summary = parsed.get('track_summary', '')

    if not timeline_json:
        raise ValueError('Timeline Agent did not return timeline_json field.')

    return ShotstackPayload(
        timeline_json=timeline_json,
        total_duration=total_duration,
        track_summary=track_summary,
    )
