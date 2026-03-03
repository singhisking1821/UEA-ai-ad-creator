"""
Revid.ai API client — V3 (fixed).

Root cause of ConnectError: The old base URL https://api.revid.ai does not resolve.
The Revid Public API v3 uses https://www.revid.ai as the base, with REST endpoints
under /api/v3/. Auth is via the header "x-api-key" (NOT "Authorization: Bearer").

References:
    - Revid Public API v3 Postman collection: https://documenter.getpostman.com/view/36975521/2sBXcGEfaB
    - Get your API key at: https://www.revid.ai/account

Environment variables required:
    REVID_API_KEY — Your Revid.ai API key (set in Railway Variables or .env)
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from utils.logger import logger

# ✅ FIXED: Correct V3 base URL (the old https://api.revid.ai does not exist)
REVID_BASE = "https://www.revid.ai"


class RevidClient:
    """
    Revid.ai API v3 client.

    Typical usage:
        client = RevidClient()
        path = await client.create_and_download(script_text, output_path)
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or config.REVID_API_KEY
        self.headers = {
            # ✅ FIXED: V3 uses "x-api-key" header, NOT "Authorization: Bearer"
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
    async def create_video(self, script: str) -> str:
        """
        Submits a video creation job to Revid.ai V3.
        Returns the video/job id string.

        V3 endpoint: POST /api/v3/videos
        Payload key: "inputText" (the script/prompt for the video)
        """
        payload = {
            "inputText": script,
            # Optional V3 fields you can add as needed:
            # "ratio": "9:16",           # portrait for Facebook/Instagram
            # "mediaType": "stockVideo", # or "aiVideo", "aiImage"
            # "language": "English",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{REVID_BASE}/api/v3/videos",
                headers=self.headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        # V3 response: { "id": "...", ... }  (top-level "id" field)
        job_id = (
            data.get("id")
            or data.get("videoId")
            or data.get("data", {}).get("id")
        )
        if not job_id:
            raise RuntimeError(
                f"Revid.ai did not return a job id. Full response: {data}"
            )

        logger.info(f"Revid.ai job submitted: {job_id}")
        return str(job_id)

    async def get_video_status(self, job_id: str) -> dict:
        """
        Returns the current status dict for a Revid.ai V3 job.

        V3 endpoint: GET /api/v3/videos/{id}
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{REVID_BASE}/api/v3/videos/{job_id}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def poll_until_complete(
        self,
        job_id: str,
        poll_interval: int = 20,
        max_wait_seconds: int = 600,
    ) -> str:
        """
        Polls Revid.ai until the video job is complete.
        Returns the video download URL.

        V3 status values: "pending" | "processing" | "completed" | "failed"
        V3 video URL field: "outputUrl"
        """
        start = time.time()
        while time.time() - start < max_wait_seconds:
            data = await self.get_video_status(job_id)

            # V3 status is at top-level "status" field
            status = (
                data.get("status")
                or data.get("data", {}).get("status")
                or ""
            ).lower()

            logger.info(f"Revid.ai job {job_id}: status={status!r}")

            if status in ("completed", "done", "finished", "success"):
                # V3 video URL field is "outputUrl"
                video_url = (
                    data.get("outputUrl")
                    or data.get("output_url")
                    or data.get("videoUrl")
                    or data.get("video_url")
                    or data.get("url")
                    or data.get("data", {}).get("outputUrl")
                    or data.get("data", {}).get("videoUrl")
                )
                if not video_url:
                    raise RuntimeError(
                        f"Revid.ai job {job_id} completed but no video URL found. "
                        f"Full response: {data}"
                    )
                logger.info(f"Revid.ai job {job_id} complete: {video_url}")
                return video_url

            elif status in ("failed", "error", "cancelled"):
                error_msg = (
                    data.get("error")
                    or data.get("message")
                    or data.get("data", {}).get("error")
                    or "Unknown Revid.ai error"
                )
                raise RuntimeError(f"Revid.ai job {job_id} failed: {error_msg}")

            await asyncio.sleep(poll_interval)

        raise TimeoutError(
            f"Revid.ai job {job_id} did not complete within {max_wait_seconds}s."
        )

    async def download_video(self, url: str, output_path: str | Path) -> Path:
        """Downloads the rendered video from the given URL to disk."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

        logger.info(f"Downloaded Revid.ai video → {output_path}")
        return output_path

    async def create_and_download(
        self,
        script: str,
        output_path: str | Path,
    ) -> Path:
        """
        End-to-end: submit script → poll until complete → download .mp4.
        Returns local path to the downloaded video.
        """
        job_id = await self.create_video(script)
        video_url = await self.poll_until_complete(job_id)
        return await self.download_video(video_url, output_path)
