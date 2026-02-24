"""
FFmpeg-based video utilities: subtitle burning, B-roll overlay,
disclaimer creation, format conversion, and final assembly.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import aiofiles

from utils.logger import logger


def run_ffmpeg(args: list[str], description: str = "") -> subprocess.CompletedProcess:
    """Run ffmpeg with the given arguments. Raises on non-zero exit."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    if description:
        logger.info(f"FFmpeg: {description}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg failed (exit={result.returncode}) cmd: {' '.join(cmd)}")
        for line in (result.stderr or result.stdout or "no output").splitlines():
            logger.error(f"  ffmpeg> {line}")
        raise RuntimeError(f"FFmpeg error: {result.stderr or result.stdout or 'no output'}")
    return result


def get_video_duration(path: str | Path) -> float:
    """Returns duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(path),
        ],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def get_video_resolution(path: str | Path) -> tuple[int, int]:
    """Returns (width, height) of the first video stream."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "v:0", str(path),
        ],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return int(stream["width"]), int(stream["height"])


def extract_audio(video_path: str | Path, output_path: str | Path) -> Path:
    """Extracts audio track from a video as MP3."""
    output_path = Path(output_path)
    run_ffmpeg(
        ["-i", str(video_path), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(output_path)],
        description=f"Extracting audio from {Path(video_path).name}",
    )
    return output_path


def create_disclaimer_clip(
    text: str,
    duration: int,
    output_path: str | Path,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """
    Creates a black screen with centered white text as the disclaimer clip.
    Text is auto-wrapped using drawtext filter.
    """
    output_path = Path(output_path)
    # Escape single quotes for ffmpeg filter
    safe_text = text.replace("'", "\\'").replace(":", "\\:")

    # Split into two lines if long
    words = text.split()
    mid = len(words) // 2
    line1 = " ".join(words[:mid]).replace("'", "\\'").replace(":", "\\:")
    line2 = " ".join(words[mid:]).replace("'", "\\'").replace(":", "\\:")

    filter_str = (
        f"color=c=black:size={width}x{height}:duration={duration}:rate=30,"
        f"drawtext=text='{line1}':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h/2)-50,"
        f"drawtext=text='{line2}':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=(h/2)+10"
    )

    run_ffmpeg(
        ["-f", "lavfi", "-i", filter_str, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output_path)],
        description="Creating disclaimer clip",
    )
    return output_path


def scale_to_portrait(input_path: str | Path, output_path: str | Path,
                       width: int = 1080, height: int = 1920) -> Path:
    """Scale and crop a video to 9:16 portrait format."""
    output_path = Path(output_path)
    # Scale to fill, then crop to exact size
    filter_str = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )
    run_ffmpeg(
        [
            "-i", str(input_path),
            "-vf", filter_str,
            "-map", "0:v",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            str(output_path),
        ],
        description=f"Scaling {Path(input_path).name} to {width}x{height}",
    )
    return output_path


def burn_subtitles(
    video_path: str | Path,
    srt_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Burns SRT subtitles into the video using ffmpeg drawsubtitle filter."""
    output_path = Path(output_path)
    # Force style for mobile-friendly subtitles
    style = (
        "FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "Outline=2,Shadow=1,Bold=1,Alignment=2,MarginV=80"
    )
    run_ffmpeg(
        [
            "-i", str(video_path),
            "-vf", f"subtitles={str(srt_path)}:force_style='{style}'",
            "-c:a", "copy",
            str(output_path),
        ],
        description="Burning subtitles",
    )
    return output_path


def overlay_broll_segments(
    avatar_path: str | Path,
    broll_clips: list[dict],  # [{"path": ..., "start": float, "end": float}]
    output_path: str | Path,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """
    Overlays B-roll clips on top of the avatar video at specified timestamps.
    Each broll_clip dict: {"path": str, "start": float, "end": float}
    """
    output_path = Path(output_path)

    if not broll_clips:
        # No B-roll, just copy
        run_ffmpeg(
            ["-i", str(avatar_path), "-c", "copy", str(output_path)],
            description="No B-roll to overlay, copying",
        )
        return output_path

    # Build complex filter graph
    inputs = ["-i", str(avatar_path)]
    for clip in broll_clips:
        inputs += ["-i", str(clip["path"])]

    filter_parts = []
    # Scale avatar as base
    filter_parts.append(f"[0:v]scale={width}:{height},setpts=PTS-STARTPTS[base]")

    prev = "[base]"
    for i, clip in enumerate(broll_clips):
        idx = i + 1
        scaled = f"[broll{idx}]"
        overlay = f"[v{idx}]"
        start = clip["start"]
        end = clip["end"]
        # Scale and crop broll to fill screen
        filter_parts.append(
            f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setpts=PTS-STARTPTS{scaled}"
        )
        filter_parts.append(
            f"{prev}{scaled}overlay=0:0:enable='between(t,{start:.2f},{end:.2f})'{overlay}"
        )
        prev = overlay

    filter_parts[-1] = filter_parts[-1].rsplit(f"[v{len(broll_clips)}]", 1)[0] + "[outv]"

    filter_complex = ";".join(filter_parts)

    run_ffmpeg(
        inputs + [
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            str(output_path),
        ],
        description=f"Overlaying {len(broll_clips)} B-roll segment(s)",
    )
    return output_path


def create_talking_head_video(
    avatar_path: str | Path,
    broll_path: str | Path,
    output_path: str | Path,
    width: int = 1080,
    height: int = 1920,
    avatar_scale: float = 0.55,
) -> Path:
    """
    Creates a 'talking head' style video:
    - B-roll fills the full background
    - Avatar is scaled and placed at the bottom center
    """
    output_path = Path(output_path)
    avatar_h = int(height * avatar_scale)
    avatar_w = int(avatar_h * (9 / 16))  # Approximate portrait avatar aspect ratio
    avatar_y = height - avatar_h - 40   # 40px from bottom
    avatar_x = (width - avatar_w) // 2

    # Get durations to loop/trim broll to match avatar
    avatar_dur = get_video_duration(avatar_path)

    filter_complex = (
        # Background: scale broll to fill frame, loop if shorter than avatar
        f"[1:v]loop=-1:size=32767,trim=duration={avatar_dur:.2f},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setpts=PTS-STARTPTS[bg];"
        # Avatar: scale down and place at bottom center
        f"[0:v]scale={avatar_w}:{avatar_h},setpts=PTS-STARTPTS[av];"
        f"[bg][av]overlay={avatar_x}:{avatar_y}[outv]"
    )

    run_ffmpeg(
        [
            "-i", str(avatar_path),
            "-i", str(broll_path),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "0:a",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "fast",
            "-t", str(avatar_dur),
            str(output_path),
        ],
        description="Creating talking-head composite",
    )
    return output_path


def concatenate_videos(video_paths: list[str | Path], output_path: str | Path) -> Path:
    """Concatenates multiple videos using FFmpeg concat demuxer."""
    output_path = Path(output_path)

    # Write a temp concat list
    list_file = Path(output_path).parent / "concat_list.txt"
    with open(list_file, "w") as f:
        for vp in video_paths:
            f.write(f"file '{Path(vp).resolve()}'\n")

    run_ffmpeg(
        [
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c:v", "libx264", "-c:a", "aac",
            "-preset", "fast",
            str(output_path),
        ],
        description=f"Concatenating {len(video_paths)} videos",
    )
    list_file.unlink(missing_ok=True)
    return output_path


def export_final(
    input_path: str | Path,
    output_path: str | Path,
    width: int = 1080,
    height: int = 1920,
    crf: int = 23,
) -> Path:
    """Final export pass: ensure correct codec, resolution, and quality."""
    output_path = Path(output_path)
    run_ffmpeg(
        [
            "-i", str(input_path),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-crf", str(crf),
            "-preset", "medium",
            "-movflags", "+faststart",
            str(output_path),
        ],
        description="Final export",
    )
    return output_path
