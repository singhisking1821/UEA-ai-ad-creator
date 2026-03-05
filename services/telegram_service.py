"""
Telegram messaging service — sends progress updates and final results to the user.
Uses the Telegram Bot API directly via httpx (no polling framework needed).
"""
from __future__ import annotations

import httpx

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

TELEGRAM_API_BASE = 'https://api.telegram.org'


async def _send_message(chat_id: int, text: str, parse_mode: str = 'HTML') -> None:
    url = f'{TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': False,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.warning(f'Telegram sendMessage failed: {resp.status_code} {resp.text}')


async def send_progress_update(chat_id: int, message: str) -> None:
    """Send a plain status update during pipeline processing."""
    logger.info(f'Telegram progress → chat {chat_id}: {message}')
    await _send_message(chat_id, message)


async def send_ad_result(chat_id: int, output) -> None:
    """Send the final result for a single completed ad."""
    drive_link = output.drive_url or output.shotstack_render_url
    text = (
        f'<b>Ad Complete</b>\n'
        f'Type: {output.ad_type} | State: {output.state}\n'
        f'Avatar: {output.avatar_key}\n'
        f'Render time: {output.render_duration_seconds:.1f}s\n'
        f'<a href="{drive_link}">View Video</a>'
    )
    await _send_message(chat_id, text)


async def send_batch_complete(chat_id: int, outputs: list) -> None:
    """Send a summary when all N ads in the batch are complete."""
    if not outputs:
        await _send_message(chat_id, 'Batch complete — no ads were produced successfully.')
        return

    lines = [f'<b>Batch Complete — {len(outputs)} ad(s) ready</b>\n']
    for i, output in enumerate(outputs, 1):
        drive_link = output.drive_url or output.shotstack_render_url
        lines.append(
            f'{i}. {output.ad_type} ({output.state}) — '
            f'<a href="{drive_link}">Watch Ad {i}</a>'
        )

    await _send_message(chat_id, '\n'.join(lines))
