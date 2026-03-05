"""
Shotstack API client — submit video render job and poll for MP4 URL.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from config.settings import settings
from models.schemas import ShotstackPayload
from utils.logger import get_logger

logger = get_logger(__name__)


def _base_url() -> str:
    return f'https://api.shotstack.io/edit/{settings.SHOTSTACK_ENV}'


def _headers() -> dict:
    return {
        'x-api-key': settings.SHOTSTACK_API_KEY,
        'Content-Type': 'application/json',
    }


async def submit_render(payload: ShotstackPayload) -> str:
    """
    Submits a render job to Shotstack.
    Returns the render_id.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f'{_base_url()}/render',
            headers=_headers(),
            json=payload.timeline_json,
        )
        resp.raise_for_status()
        data = resp.json()

    render_id = data.get('response', {}).get('id')
    if not render_id:
        raise RuntimeError(f'Shotstack did not return render id: {data}')
    logger.info(f'Shotstack render submitted: {render_id}')
    return render_id


async def poll_render_status(render_id: str, timeout_seconds: int = 300) -> str:
    """
    Polls Shotstack until the render is complete.
    Returns the direct MP4 URL when status == 'done'.
    Raises RuntimeError on failure, TimeoutError on timeout.
    """
    poll_interval = 10
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=30) as client:
        while time.monotonic() - start < timeout_seconds:
            resp = await client.get(
                f'{_base_url()}/render/{render_id}',
                headers=_headers(),
            )
            resp.raise_for_status()
            data = resp.json()
            render_data = data.get('response', {})
            status = render_data.get('status', '')
            logger.info(f'Shotstack render {render_id}: status={status}')

            if status == 'done':
                url = render_data.get('url')
                if not url:
                    raise RuntimeError('Shotstack done but no url in response.')
                return url
            elif status == 'failed':
                error = render_data.get('error', 'unknown error')
                raise RuntimeError(f'Shotstack render failed: {error}')

            await asyncio.sleep(poll_interval)

    raise TimeoutError(
        f'Shotstack render {render_id} did not complete within {timeout_seconds}s'
    )
