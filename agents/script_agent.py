"""
Script Agent — Claude Sonnet 4.6 call #1.
Generates N unique USAEA ad scripts with avatar selection and timing validation.
"""
from __future__ import annotations

import json
import re

import anthropic

from config.avatars import get_avatar_list_for_claude
from config.settings import settings
from models.schemas import AdRequest, AdScript
from prompts.script_agent_prompt import SCRIPT_AGENT_SYSTEM_PROMPT
from services import google_sheets
from utils.logger import get_logger
from utils.timing import estimate_duration

logger = get_logger(__name__)


def _strip_json_fences(text: str) -> str:
    """Remove markdown code fences if Claude wrapped the JSON."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


async def generate_scripts(request: AdRequest) -> list[AdScript]:
    """
    Generates N unique USAEA ad scripts for the given AdRequest.
    Steps:
      1. Fetch script history from Sheets for deduplication context
      2. Call Claude Sonnet 4.6 with the full USAEA system prompt
      3. Validate timing — re-call Claude to shorten any script > 22s
      4. Log all scripts to Sheets immediately (before downstream steps)
      5. Return validated list of AdScript objects
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    avatar_list = get_avatar_list_for_claude()

    # Step 1: fetch history for deduplication
    history = await google_sheets.get_recent_scripts(limit=30)
    last_cta = await google_sheets.get_last_cta_used()

    # Step 2: build user message
    user_msg = (
        f'Generate {request.count} unique USAEA ad script(s).\n\n'
        f'Ad Type: {request.ad_type}\n'
        f'State: {request.state}\n'
        f'Number of ads to generate: {request.count}\n\n'
        f'Available Avatars:\n{avatar_list}\n\n'
        f'Last CTA used for this ad_type: {last_cta or "none yet"}\n\n'
        f'Script History (last {len(history)} entries — do not repeat hooks, '
        f'body angles, or CTAs):\n'
        f'{json.dumps(history, indent=2, default=str)}'
    )

    logger.info(
        f'Calling Script Agent for {request.count} {request.ad_type} ad(s) — '
        f'{request.state}'
    )

    # Step 3: call Claude
    response = await client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=4000,
        system=SCRIPT_AGENT_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': user_msg}],
    )
    raw = response.content[0].text
    logger.info(f'Script Agent response: {len(raw)} chars')

    # Step 4: parse and validate
    scripts: list[AdScript] = []
    try:
        parsed = json.loads(_strip_json_fences(raw))
        if isinstance(parsed, dict):
            parsed = [parsed]
    except json.JSONDecodeError as exc:
        raise ValueError(
            f'Script Agent returned invalid JSON: {exc}\nRaw (first 400): {raw[:400]}'
        )

    for item in parsed:
        script = AdScript(**item)

        # Validate and fix timing — spoken script must leave 3.5s for end screen
        max_spoken = settings.MAX_VIDEO_SECONDS - 3.5
        actual_seconds = estimate_duration(script.full_script)
        if actual_seconds > max_spoken:
            logger.warning(
                f'Script {script.script_id} estimated {actual_seconds:.1f}s > '
                f'{max_spoken:.1f}s spoken limit — requesting shorten'
            )
            script = await _shorten_script(client, script)

        scripts.append(script)

    if not scripts:
        raise ValueError('Script Agent produced no parseable scripts.')

    # Step 5: log to Sheets immediately before any downstream failure
    await google_sheets.log_scripts(scripts)
    logger.info(f'Logged {len(scripts)} script(s) to Script Log tab')

    return scripts


async def _shorten_script(
    client: anthropic.AsyncAnthropic,
    script: AdScript,
) -> AdScript:
    """Re-calls Claude with a targeted instruction to shorten the body only."""
    shorten_msg = (
        f'This script is too long. Shorten it to under 18.5 seconds of spoken time by cutting '
        f'words from the body ONLY. Keep the hook, CTA, and avatar_key identical. '
        f'Return a JSON array with exactly one script object.\n\n'
        f'Script to shorten:\n{json.dumps(script.model_dump(mode="json"), indent=2, default=str)}'
    )
    response = await client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=1000,
        system=SCRIPT_AGENT_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': shorten_msg}],
    )
    raw = response.content[0].text
    parsed = json.loads(_strip_json_fences(raw))
    if isinstance(parsed, list) and parsed:
        return AdScript(**parsed[0])
    return AdScript(**parsed)
