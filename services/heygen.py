"""
HeyGen API v2 client — submit talking head video + poll for completion.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from config.avatars import AvatarConfig
from config.settings import settings
from models.schemas import AdScript
from utils.logger import get_logger

logger = get_logger(__name__)

HEYGEN_BASE = 'https://api.heygen.com'


async def create_talking_head_video(script: AdScript, avatar: AvatarConfig) -> str:
    """
    Submits a talking head video generation job to HeyGen v2.
    Returns the video_id to poll for status.
    """
    character: dict = {
        'type': 'avatar',
        'avatar_id': avatar['avatar_id'],
        'avatar_style': 'normal',
    }
    if avatar.get('look_id'):
        character['avatar_look_id'] = avatar['look_id']

    payload = {
        'video_inputs': [
            {
                'character': character,
                'voice': {
                    'type': 'text',
                    'input_text': script.full_script,
                    'voice_id': avatar['voice_id'],
                    'speed': 1.0,
                },
            }
        ],
        'dimension': {'width': 1080, 'height': 1920},
        'aspect_ratio': None,
    }

    headers = {
        'X-Api-Key': settings.HEYGEN_API_KEY,
        'Content-Type': 'application/json',
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f'{HEYGEN_BASE}/v2/video/generate',
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    video_id = data.get('data', {}).get('video_id')
    if not video_id:
        raise RuntimeError(f'HeyGen did not return video_id: {data}')
    logger.info(f'HeyGen video job submitted: {video_id}')
    return video_id


async def poll_video_status(video_id: str, timeout_seconds: int = 300) -> str:
    """
    Polls HeyGen until the video is complete.
    Returns the direct video_url when status == 'completed'.
    Raises TimeoutError if not completed within timeout_seconds.
    """
    headers = {'X-Api-Key': settings.HEYGEN_API_KEY}
    poll_interval = 10
    start = time.monotonic()

    async with httpx.AsyncClient(timeout=30) as client:
        while time.monotonic() - start < timeout_seconds:
            resp = await client.get(
                f'{HEYGEN_BASE}/v1/video_status.get',
                headers=headers,
                params={'video_id': video_id},
            )
            resp.raise_for_status()
            data = resp.json().get('data', {})
            status = data.get('status', '')
            logger.info(f'HeyGen video {video_id}: status={status}')

            if status == 'completed':
                url = data.get('video_url')
                if not url:
                    raise RuntimeError('HeyGen completed but no video_url returned.')
                return url
            elif status in ('failed', 'error'):
                raise RuntimeError(f'HeyGen video generation failed: {data}')

            await asyncio.sleep(poll_interval)

    raise TimeoutError(
        f'HeyGen video {video_id} did not complete within {timeout_seconds}s'
    )
