"""
Uploader Agent: uploads final videos to Google Drive and logs them to Google Sheets.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from agents.quality_checker import QCResult
from agents.script_writer import AdScript
from services.google_drive import GoogleDriveClient
from services.google_sheets import GoogleSheetsClient
from utils.logger import logger


async def upload_and_log(
    script: AdScript,
    video_path: Path,
    qc_result: QCResult,
    website: str,
    progress_cb=None,
) -> Optional[str]:
    """
    Uploads one video to Drive and logs it to Sheets.
    Returns the Google Drive shareable link, or None on failure.
    """
    def notify(msg):
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    notify(f"☁️ Uploading Ad #{script.number} to Google Drive...")

    try:
        drive = GoogleDriveClient()
        sheets = GoogleSheetsClient()

        # Generate a descriptive filename
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"ad_{script.number:02d}_{script.ad_type}_{date_str}.mp4"

        # Upload (run in thread to avoid blocking event loop)
        link = await asyncio.to_thread(drive.upload_video, video_path, filename)

        # Log to Sheets
        status = "Ready" if qc_result.passed else f"Issues: {'; '.join(qc_result.issues[:2])}"
        script_preview = script.script_text[:100] + "..." if len(script.script_text) > 100 else script.script_text

        await asyncio.to_thread(
            sheets.append_ad_record,
            website,
            script.number,
            script.ad_type,
            script_preview,
            link,
            status,
        )

        notify(f"✅ Ad #{script.number} uploaded: {link}")
        return link

    except Exception as e:
        logger.error(f"Upload failed for Ad #{script.number}: {e}")
        if progress_cb:
            progress_cb(f"⚠️ Upload failed for Ad #{script.number}: {e}")
        return None


async def upload_all_ads(
    scripts: list[AdScript],
    final_videos: dict[int, Path],
    qc_results: dict[int, QCResult],
    website: str,
    progress_cb=None,
    max_concurrent: int = 3,
) -> dict[int, str]:
    """
    Uploads all final videos to Google Drive and logs them.
    Returns {script_number: drive_link}.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results: dict[int, str] = {}

    async def _upload_one(script: AdScript):
        async with semaphore:
            video_path = final_videos.get(script.number)
            qc = qc_results.get(script.number)
            if not video_path or not qc:
                logger.error(f"Missing video or QC result for Ad #{script.number}")
                return
            link = await upload_and_log(script, video_path, qc, website, progress_cb)
            if link:
                results[script.number] = link

    await asyncio.gather(*[_upload_one(s) for s in scripts if s.number in final_videos])
    return results
