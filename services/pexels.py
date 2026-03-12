"""
Pexels API client — search for stock video clips and return direct MP4 URLs.
"""
from __future__ import annotations

import httpx

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

PEXELS_VIDEO_BASE = 'https://api.pexels.com/videos'


async def search_clips(query: str, per_page: int = 5) -> list[dict]:
    """
    Searches Pexels for landscape video clips matching the query.
    Returns a list of video objects with: id, url, duration, video_files array.
    """
    headers = {'Authorization': settings.PEXELS_API_KEY}
    params = {
        'query': query,
        'per_page': per_page,
        'orientation': 'portrait',
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f'{PEXELS_VIDEO_BASE}/search',
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

    videos = data.get('videos', [])
    logger.info(f"Pexels search '{query}': {len(videos)} results")
    return videos


def select_best_clip(
    results: list[dict],
    target_duration_range: tuple[int, int] = (4, 8),
) -> dict | None:
    """
    Selects the best clip from Pexels search results.
    - Prefers clips within target_duration_range (seconds)
    - Prefers HD quality (1280x720 minimum)
    Returns a dict with 'clip_url' (direct mp4 link) and 'duration_seconds',
    or None if no suitable clip found.
    """
    min_dur, max_dur = target_duration_range

    def _best_file(video: dict) -> dict | None:
        files = video.get('video_files', [])
        hd_files = [
            f for f in files
            if f.get('file_type') == 'video/mp4'
            and f.get('width', 0) >= 1280
            and f.get('height', 0) >= 720
            and f.get('link')
        ]
        if hd_files:
            hd_files.sort(key=lambda f: f.get('width', 0), reverse=True)
            return hd_files[0]
        mp4_files = [
            f for f in files
            if f.get('file_type') == 'video/mp4' and f.get('link')
        ]
        if mp4_files:
            mp4_files.sort(key=lambda f: f.get('width', 0), reverse=True)
            return mp4_files[0]
        return None

    # First pass: prefer clips in target duration range
    for video in results:
        duration = video.get('duration', 0)
        if min_dur <= duration <= max_dur:
            file_info = _best_file(video)
            if file_info:
                return {
                    'clip_url': file_info['link'],
                    'duration_seconds': float(duration),
                }

    # Second pass: accept any clip from results
    for video in results:
        file_info = _best_file(video)
        if file_info:
            return {
                'clip_url': file_info['link'],
                'duration_seconds': float(video.get('duration', 0)),
            }

    return None
