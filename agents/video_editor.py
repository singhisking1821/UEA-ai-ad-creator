"""
Video Editor Agent: assembles the final ad video.

Pipeline per ad:
1. Scale avatar video to portrait (1080x1920)
2. Generate subtitles via OpenAI Whisper
3. Overlay B-roll at specified timestamps
4. For talking_head: composite avatar over B-roll background
5. Add disclaimer screen at the end
6. Burn subtitles
7. Final export
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import openai

import config
from agents.script_writer import AdScript
from utils.logger import logger
from utils import video_utils as vu


async def _generate_subtitles_whisper(audio_path: Path, output_srt: Path) -> Optional[Path]:
    """Uses OpenAI Whisper API to generate SRT subtitles from audio."""
    try:
        client = openai.OpenAI(api_key=config.OPENAI_API_KEY)
        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="srt",
            )
        # transcript is the SRT string
        with open(output_srt, "w", encoding="utf-8") as f:
            f.write(transcript)
        logger.info(f"Subtitles generated → {output_srt}")
        return output_srt
    except Exception as e:
        logger.warning(f"Whisper subtitle generation failed: {e}")
        return None


def _run_sync(coro):
    """Run a coroutine synchronously (for use in sync contexts)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def edit_full_broll_ad(
    script: AdScript,
    avatar_path: Path,
    broll_clips: list[dict],
    output_path: Path,
    temp_dir: Path,
    progress_cb=None,
) -> Path:
    """
    Assembles a 'Full Video + B-roll' style ad:
    - Avatar fills screen
    - B-roll overlaid at specified timestamps
    - Subtitles burned in
    - Disclaimer appended
    """
    ad_temp = temp_dir / f"edit_ad_{script.number:02d}"
    ad_temp.mkdir(parents=True, exist_ok=True)

    def notify(msg):
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    notify(f"✂️ Editing Ad #{script.number} (Full B-roll style)")

    # Step 1: Scale avatar to portrait
    scaled_avatar = ad_temp / "avatar_scaled.mp4"
    await asyncio.to_thread(
        vu.scale_to_portrait, avatar_path, scaled_avatar,
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    )

    # Step 2: Extract audio for subtitles
    audio_path = ad_temp / "audio.mp3"
    await asyncio.to_thread(vu.extract_audio, scaled_avatar, audio_path)

    # Step 3: Generate subtitles
    srt_path = ad_temp / "subtitles.srt"
    srt_result = await _generate_subtitles_whisper(audio_path, srt_path)

    # Step 4: Overlay B-roll on avatar
    brolled_path = ad_temp / "with_broll.mp4"
    await asyncio.to_thread(
        vu.overlay_broll_segments,
        scaled_avatar, broll_clips, brolled_path,
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT,
    )

    # Step 5: Burn subtitles (if generated)
    if srt_result and srt_result.exists():
        subbed_path = ad_temp / "with_subtitles.mp4"
        await asyncio.to_thread(vu.burn_subtitles, brolled_path, srt_result, subbed_path)
    else:
        subbed_path = brolled_path
        notify(f"⚠️ No subtitles generated for Ad #{script.number}")

    # Step 6: Create disclaimer clip
    disclaimer_path = ad_temp / "disclaimer.mp4"
    await asyncio.to_thread(
        vu.create_disclaimer_clip,
        config.DISCLAIMER_TEXT,
        config.DISCLAIMER_DURATION_SECONDS,
        disclaimer_path,
        config.VIDEO_WIDTH,
        config.VIDEO_HEIGHT,
    )

    # Step 7: Concatenate main video + disclaimer
    combined_path = ad_temp / "combined.mp4"
    await asyncio.to_thread(
        vu.concatenate_videos, [subbed_path, disclaimer_path], combined_path
    )

    # Step 8: Final export
    await asyncio.to_thread(
        vu.export_final, combined_path, output_path,
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    )

    notify(f"✅ Ad #{script.number} editing complete → {output_path.name}")
    return output_path


async def edit_talking_head_ad(
    script: AdScript,
    avatar_path: Path,
    broll_clips: list[dict],
    output_path: Path,
    temp_dir: Path,
    progress_cb=None,
) -> Path:
    """
    Assembles a 'Talking Head' style ad:
    - First B-roll clip (or a selected one) fills the background
    - Avatar is scaled and placed at the bottom of the screen
    - Subtitles burned in
    - Disclaimer appended
    """
    ad_temp = temp_dir / f"edit_ad_{script.number:02d}"
    ad_temp.mkdir(parents=True, exist_ok=True)

    def notify(msg):
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    notify(f"✂️ Editing Ad #{script.number} (Talking Head style)")

    # Pick a background B-roll (use the first available, or a generic one)
    bg_broll_path: Optional[Path] = None
    if broll_clips:
        bg_broll_path = Path(broll_clips[0]["path"])

    # If no B-roll available, use a solid color background
    if not bg_broll_path or not bg_broll_path.exists():
        # Create a simple gradient background
        bg_broll_path = ad_temp / "bg_color.mp4"
        avatar_dur = vu.get_video_duration(avatar_path)
        vu.run_ffmpeg(
            [
                "-f", "lavfi",
                "-i", f"color=c=0x1a3a5c:size={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}:duration={avatar_dur}:rate=30",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(bg_broll_path),
            ],
            description="Creating fallback background",
        )

    # Step 1: Create talking head composite
    talking_head_path = ad_temp / "talking_head.mp4"
    await asyncio.to_thread(
        vu.create_talking_head_video,
        avatar_path, bg_broll_path, talking_head_path,
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT,
    )

    # Step 2: Extract audio for subtitles
    audio_path = ad_temp / "audio.mp3"
    await asyncio.to_thread(vu.extract_audio, talking_head_path, audio_path)

    # Step 3: Subtitles
    srt_path = ad_temp / "subtitles.srt"
    srt_result = await _generate_subtitles_whisper(audio_path, srt_path)

    if srt_result and srt_result.exists():
        subbed_path = ad_temp / "with_subtitles.mp4"
        await asyncio.to_thread(vu.burn_subtitles, talking_head_path, srt_result, subbed_path)
    else:
        subbed_path = talking_head_path

    # Step 4: Disclaimer
    disclaimer_path = ad_temp / "disclaimer.mp4"
    await asyncio.to_thread(
        vu.create_disclaimer_clip,
        config.DISCLAIMER_TEXT,
        config.DISCLAIMER_DURATION_SECONDS,
        disclaimer_path,
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT,
    )

    # Step 5: Concatenate
    combined_path = ad_temp / "combined.mp4"
    await asyncio.to_thread(
        vu.concatenate_videos, [subbed_path, disclaimer_path], combined_path
    )

    # Step 6: Final export
    await asyncio.to_thread(
        vu.export_final, combined_path, output_path,
        config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    )

    notify(f"✅ Ad #{script.number} editing complete → {output_path.name}")
    return output_path


async def edit_ad(
    script: AdScript,
    avatar_path: Path,
    broll_clips: list[dict],
    output_dir: Path,
    temp_dir: Path,
    progress_cb=None,
) -> Optional[Path]:
    """
    Dispatches to the correct editor based on ad_type.
    Returns path to final video or None if editing failed.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"final_ad_{script.number:02d}.mp4"

    try:
        if script.ad_type == "talking_head":
            return await edit_talking_head_ad(
                script, avatar_path, broll_clips, output_path, temp_dir, progress_cb
            )
        else:
            return await edit_full_broll_ad(
                script, avatar_path, broll_clips, output_path, temp_dir, progress_cb
            )
    except Exception as e:
        logger.error(f"Video editing failed for Ad #{script.number}: {e}")
        if progress_cb:
            progress_cb(f"⚠️ Editing failed for Ad #{script.number}: {e}")
        return None


async def edit_all_ads(
    scripts: list[AdScript],
    avatar_paths: dict[int, Path],
    broll_clips: dict[int, list[dict]],
    output_dir: Path,
    temp_dir: Path,
    progress_cb=None,
    max_concurrent: int = 2,
) -> dict[int, Path]:
    """
    Edits all ads with limited concurrency.
    Returns {script_number: final_video_path}.
    """
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)
    results: dict[int, Path] = {}

    async def _edit_one(script: AdScript):
        async with semaphore:
            avatar = avatar_paths.get(script.number)
            if not avatar:
                logger.error(f"No avatar video for script #{script.number}, skipping")
                return
            clips = broll_clips.get(script.number, [])
            path = await edit_ad(script, avatar, clips, output_dir, temp_dir, progress_cb)
            if path:
                results[script.number] = path

    await asyncio.gather(*[_edit_one(s) for s in scripts])
    return results
