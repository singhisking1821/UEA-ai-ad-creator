"""
Master async pipeline — coordinates all agents and services for the USAEA Ad Factory.
Handles N ads in parallel with progress updates to Telegram.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime

import anthropic

from agents import broll_agent, script_agent, timeline_agent
from config.avatars import AVATARS
from config.settings import settings
from models.schemas import AdOutput, AdRequest, AdScript
from services import google_drive, google_sheets, shotstack, telegram_service
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Prompt parsing ────────────────────────────────────────────────────────────

_AD_TYPE_PATTERNS = [
    (r'wrongful\s+termination', 'wrongful termination'),
    (r'wage\s+theft|wage\s+dispute|unpaid\s+wages?', 'wage theft'),
    (r'discriminat', 'discrimination'),
    (r'retaliation', 'retaliation'),
    (r'harassment', 'harassment'),
]

_STATE_PATTERN = re.compile(
    r'\b(california|texas|florida|new york|illinois|ohio|georgia|'
    r'north carolina|michigan|new jersey|virginia|washington|arizona|'
    r'massachusetts|tennessee|indiana|missouri|maryland|wisconsin|'
    r'colorado|minnesota|south carolina|alabama|louisiana|kentucky|'
    r'oregon|oklahoma|connecticut|utah|iowa|nevada|arkansas|'
    r'mississippi|kansas|new mexico|nebraska|idaho|west virginia|'
    r'hawaii|new hampshire|maine|montana|rhode island|delaware|'
    r'south dakota|north dakota|alaska|vermont|wyoming)\b',
    re.IGNORECASE,
)

_COUNT_PATTERN = re.compile(r'\b(\d+)\b')


def _parse_with_regex(message: str) -> AdRequest | None:
    """Fast regex parser for well-formed prompts. Returns None if uncertain."""
    text = message.lower()

    # Ad type
    ad_type = 'wrongful termination'  # default
    for pattern, label in _AD_TYPE_PATTERNS:
        if re.search(pattern, text):
            ad_type = label
            break

    # State
    state_match = _STATE_PATTERN.search(message)
    state = state_match.group(0).title() if state_match else 'California'

    # Count
    count_matches = _COUNT_PATTERN.findall(text)
    count = int(count_matches[0]) if count_matches else 1
    count = max(1, min(count, settings.MAX_ADS_PER_BATCH))

    return AdRequest(
        raw_prompt=message,
        ad_type=ad_type,
        state=state,
        count=count,
        chat_id=0,  # caller sets this
    )


async def _parse_with_haiku(message: str) -> AdRequest:
    """Uses Claude Haiku to parse ambiguous prompts."""
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    system = (
        'Parse the user message and return ONLY a JSON object with these fields:\n'
        '{"ad_type": "<wrongful termination|wage theft|discrimination|retaliation|harassment>", '
        '"state": "<US state name, default California>", '
        '"count": <integer 1-10>}\n'
        'No prose, no markdown. Just the JSON object.'
    )
    response = await client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=100,
        system=system,
        messages=[{'role': 'user', 'content': message}],
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    parsed = json.loads(raw)
    return AdRequest(
        raw_prompt=message,
        ad_type=parsed.get('ad_type', 'wrongful termination'),
        state=parsed.get('state', 'California'),
        count=max(1, min(int(parsed.get('count', 1)), settings.MAX_ADS_PER_BATCH)),
        chat_id=0,
    )


async def parse_telegram_prompt(message: str, chat_id: int) -> AdRequest:
    """
    Parses a natural language Telegram message into a structured AdRequest.
    Uses regex for clear patterns; falls back to Claude Haiku for ambiguous ones.
    """
    request = _parse_with_regex(message)
    if request is None:
        request = await _parse_with_haiku(message)

    request.chat_id = chat_id
    logger.info(
        f'Parsed request: ad_type={request.ad_type} state={request.state} '
        f'count={request.count}'
    )
    return request


# ── Single-ad pipeline ────────────────────────────────────────────────────────

async def run_single_ad(script: AdScript, ad_index: int, chat_id: int) -> AdOutput:
    """
    Full pipeline for one ad:
      HeyGen → B-roll fetch → Timeline build → Shotstack render → Drive upload → log
    """
    start_time = time.monotonic()
    n = ad_index

    # Get avatar config
    avatar = AVATARS.get(script.avatar_key)
    if not avatar:
        raise ValueError(f'Unknown avatar_key: {script.avatar_key}')

    # HeyGen talking head
    await telegram_service.send_progress_update(
        chat_id, f'Creating HeyGen video for ad {n}...'
    )
    from services.heygen import create_talking_head_video, poll_video_status
    video_id = await create_talking_head_video(script, avatar)
    heygen_url = await poll_video_status(video_id, timeout_seconds=600)
    logger.info(f'Ad {n}: HeyGen video ready: {heygen_url[:60]}...')

    # B-roll
    await telegram_service.send_progress_update(
        chat_id, f'Finding B-roll for ad {n}...'
    )
    broll_clips = await broll_agent.get_broll_clips(script)
    logger.info(f'Ad {n}: {len(broll_clips)} B-roll clip(s) fetched')

    # Shotstack timeline
    await telegram_service.send_progress_update(
        chat_id, f'Building video timeline for ad {n}...'
    )
    payload = await timeline_agent.build_shotstack_payload(script, heygen_url, broll_clips)

    # Shotstack render
    await telegram_service.send_progress_update(
        chat_id, f'Rendering ad {n} with Shotstack...'
    )
    render_id = await shotstack.submit_render(payload)
    mp4_url = await shotstack.poll_render_status(render_id, timeout_seconds=300)
    logger.info(f'Ad {n}: Shotstack render complete: {mp4_url[:60]}...')

    # Drive upload
    date_str = datetime.utcnow().strftime('%Y%m%d')
    filename = (
        f'USAEA_{script.ad_type.replace(" ", "_")}_{script.state}_{date_str}_'
        f'Ad{n}_{script.script_id[:8]}.mp4'
    )
    drive_url = await google_drive.upload_video(mp4_url, filename)

    render_secs = time.monotonic() - start_time
    output = AdOutput(
        script_id=script.script_id,
        ad_type=script.ad_type,
        state=script.state,
        avatar_key=script.avatar_key,
        heygen_video_url=heygen_url,
        shotstack_render_url=mp4_url,
        drive_url=drive_url,
        render_duration_seconds=round(render_secs, 1),
    )

    await google_sheets.log_output(output)
    await telegram_service.send_ad_result(chat_id, output)
    logger.info(f'Ad {n} complete in {render_secs:.0f}s')
    return output


# ── Top-level pipeline ────────────────────────────────────────────────────────

async def run_pipeline(request: AdRequest) -> list[AdOutput]:
    """
    Top-level pipeline — generates N scripts and runs all ads in parallel.
    Partial failures are caught and logged; successful outputs are returned.
    """
    logger.info(
        f'Pipeline start: {request.count} {request.ad_type} ad(s) for {request.state}'
    )
    await telegram_service.send_progress_update(
        request.chat_id,
        f'Starting batch of {request.count} {request.ad_type} ad(s) for {request.state}...',
    )

    # Generate all scripts (also logs them to Sheets for deduplication)
    await telegram_service.send_progress_update(
        request.chat_id, 'Generating ad scripts...'
    )
    scripts = await script_agent.generate_scripts(request)
    logger.info(f'Generated {len(scripts)} script(s)')

    # Run all ads in parallel
    tasks = [
        run_single_ad(script, i + 1, request.chat_id)
        for i, script in enumerate(scripts)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    outputs: list[AdOutput] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f'Ad {i + 1} failed: {result}')
            await telegram_service.send_progress_update(
                request.chat_id, f'Ad {i + 1} failed: {result}'
            )
        else:
            outputs.append(result)

    await telegram_service.send_batch_complete(request.chat_id, outputs)
    logger.info(
        f'Pipeline complete: {len(outputs)}/{len(scripts)} ads succeeded'
    )
    return outputs
