"""
Video Generator Agent: uses HeyGen to create AI avatar videos from scripts.
Handles retry, progress reporting, and downloading.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from agents.script_writer import AdScript
from services.heygen import HeyGenClient
import config
from utils.logger import logger


async def generate_avatar_video(
    script: AdScript,
    output_dir: Path,
    avatar_id: Optional[str] = None,
    voice_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Path:
    """
    Generates a HeyGen avatar video for a given AdScript.
    Returns the path to the downloaded .mp4 file.

    progress_cb: optional async/sync callable for status updates (e.g., Telegram messages)
    """
    client = HeyGenClient()
    output_path = output_dir / f"avatar_ad_{script.number:02d}.mp4"

    def _notify(msg: str):
        logger.info(msg)
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    _notify(f"🎬 Generating avatar video for Ad #{script.number} ({script.angle})")

    try:
        path = await client.create_video(
            script=script.script_text,
            output_path=output_path,
            avatar_id=avatar_id,
            voice_id=voice_id,
            width=config.VIDEO_WIDTH,
            height=config.VIDEO_HEIGHT,
        )
        _notify(f"✅ Avatar video #{script.number} downloaded ({path.stat().st_size // 1024} KB)")
        return path

    except Exception as e:
        logger.error(f"Avatar generation failed for script #{script.number}: {e}")
        raise


async def generate_all_avatar_videos(
    scripts: list[AdScript],
    output_dir: Path,
    avatar_id: Optional[str] = None,
    voice_id: Optional[str] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
    max_concurrent: int = 2,
) -> dict[int, Path]:
    """
    Generates avatar videos for all scripts.
    Limits concurrency to avoid rate limits.
    Returns {script_number: local_path}.
    """
    import asyncio

    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[int, Path] = {}
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _generate_one(script: AdScript):
        async with semaphore:
            try:
                path = await generate_avatar_video(
                    script, output_dir, avatar_id, voice_id, progress_cb
                )
                results[script.number] = path
            except Exception as e:
                logger.error(f"Script #{script.number} avatar failed: {e}")
                if progress_cb:
                    progress_cb(f"⚠️ Ad #{script.number} avatar generation failed: {e}")

    tasks = [_generate_one(s) for s in scripts]
    await asyncio.gather(*tasks)
    return results
