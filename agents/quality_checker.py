"""
Quality Checker Agent: validates final video files before upload.
Checks duration, resolution, file size, and audio presence.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from utils.logger import logger
from utils.video_utils import get_video_duration, get_video_resolution
import config


@dataclass
class QCResult:
    ad_number: int
    passed: bool
    issues: list[str]
    duration_seconds: float
    resolution: tuple[int, int]
    file_size_mb: float


def _has_audio_stream(path: Path) -> bool:
    """Returns True if the video has an audio stream."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-select_streams", "a:0", str(path),
        ],
        capture_output=True, text=True,
    )
    try:
        data = json.loads(result.stdout)
        return len(data.get("streams", [])) > 0
    except Exception:
        return False


def check_video(ad_number: int, video_path: Path) -> QCResult:
    """
    Runs quality checks on a final video.
    Returns a QCResult with pass/fail status.
    """
    issues = []

    if not video_path.exists():
        return QCResult(
            ad_number=ad_number,
            passed=False,
            issues=["File does not exist"],
            duration_seconds=0,
            resolution=(0, 0),
            file_size_mb=0,
        )

    # File size
    size_bytes = video_path.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    if size_mb < 1:
        issues.append(f"File too small ({size_mb:.1f} MB) — likely corrupt")
    if size_mb > 500:
        issues.append(f"File very large ({size_mb:.1f} MB) — may need compression")

    # Duration
    try:
        duration = get_video_duration(video_path)
    except Exception as e:
        issues.append(f"Could not read duration: {e}")
        duration = 0

    if duration < 10:
        issues.append(f"Duration too short ({duration:.1f}s) — something went wrong")
    elif duration > 180:
        issues.append(f"Duration very long ({duration:.1f}s) — check if expected")

    # Resolution
    try:
        resolution = get_video_resolution(video_path)
    except Exception as e:
        issues.append(f"Could not read resolution: {e}")
        resolution = (0, 0)

    w, h = resolution
    if w != config.VIDEO_WIDTH or h != config.VIDEO_HEIGHT:
        issues.append(
            f"Resolution mismatch: got {w}x{h}, expected {config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT}"
        )

    # Audio
    if not _has_audio_stream(video_path):
        issues.append("No audio stream detected — video will be silent")

    passed = len(issues) == 0
    status = "✅ PASS" if passed else f"⚠️ ISSUES ({len(issues)})"
    logger.info(
        f"QC Ad #{ad_number}: {status} | {duration:.1f}s | {w}x{h} | {size_mb:.1f} MB"
    )
    for issue in issues:
        logger.warning(f"  - Ad #{ad_number}: {issue}")

    return QCResult(
        ad_number=ad_number,
        passed=passed,
        issues=issues,
        duration_seconds=duration,
        resolution=resolution,
        file_size_mb=size_mb,
    )


def check_all_ads(final_videos: dict[int, Path]) -> dict[int, QCResult]:
    """Runs QC on all final videos. Returns {ad_number: QCResult}."""
    return {num: check_video(num, path) for num, path in final_videos.items()}


def format_qc_report(qc_results: dict[int, QCResult]) -> str:
    """Returns a human-readable QC summary string."""
    lines = ["*QC Report*"]
    for num, result in sorted(qc_results.items()):
        status = "✅" if result.passed else "⚠️"
        lines.append(
            f"{status} Ad #{num}: {result.duration_seconds:.1f}s | "
            f"{result.resolution[0]}x{result.resolution[1]} | "
            f"{result.file_size_mb:.1f} MB"
        )
        for issue in result.issues:
            lines.append(f"    • {issue}")
    return "\n".join(lines)
