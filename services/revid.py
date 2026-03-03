"""
Revid.ai / Typeframes API client — V2.

Revid.ai and Typeframes share the same API.
Base URL: https://api.typeframes.com
Auth header: "key" (your API key from https://www.revid.ai/account)
Endpoint: POST /v2/videos

References:
    - Typeframes Public API V2 Postman collection:
      https://documenter.getpostman.com/view/3209066/2sA3JDgjpp
    - Get your API key at: https://www.revid.ai/account

Environment variables required:
    REVID_API_KEY — Your Revid.ai / Typeframes API key
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from utils.logger import logger

REVID_BASE = "https://api.typeframes.com"


class RevidClient:
    """
    Revid.ai / Typeframes API V2 client.

    Typical usage:
        client = RevidClient()
        path = await client.create_and_download(script_text, output_path)
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or config.REVID_API_KEY
        self.headers = {
            "key": self.api_key,
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
    async def create_video(self, script: str) -> str:
        """
        Submits a video creation job to Revid.ai / Typeframes V2.
        Returns the video/job id string.

        Endpoint: POST /v2/videos
        """
        payload = {
            "template": "tiktok",
            "inputs": {
                "text": script,
            },
        }

        logger.info(
            f"Revid.ai: submitting video creation to {REVID_BASE}/v2/videos "
            f"(text length={len(script)} chars)"
        )

        async with httpx.AsyncClient(timeout=90) as client:
            resp = await client.post(
                f"{REVID_BASE}/v2/videos",
                headers=self.headers,
                json=payload,
            )
            # Log the raw response BEFORE raise_for_status so we can debug errors
            logger.info(
                f"Revid.ai create response [{resp.status_code}]: "
                f"{resp.text[:1000]}"
            )
            resp.raise_for_status()
            data = resp.json()

        # Try multiple possible response field names for the job/video ID
        job_id = (
            data.get("id")
            or data.get("videoId")
            or data.get("video_id")
            or data.get("taskId")
            or data.get("task_id")
            or data.get("data", {}).get("id")
            or data.get("data", {}).get("videoId")
        )
        if not job_id:
            raise RuntimeError(
                f"Revid.ai did not return a job id. Full response: {data}"
            )

        logger.info(f"Revid.ai job submitted: {job_id}")
        return str(job_id)

    async def get_video_status(self, job_id: str) -> dict:
        """
        Returns the current status dict for a Revid.ai job.

        Tries GET /v2/videos/{id} (common REST pattern).
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{REVID_BASE}/v2/videos/{job_id}",
                headers=self.headers,
            )
            logger.info(
                f"Revid.ai status response [{resp.status_code}]: "
                f"{resp.text[:1000]}"
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
        """
        start = time.time()
        while time.time() - start < max_wait_seconds:
            try:
                data = await self.get_video_status(job_id)
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"Revid.ai status poll error [{e.response.status_code}]: "
                    f"{e.response.text[:500]}  — will retry..."
                )
                await asyncio.sleep(poll_interval)
                continue

            # Try multiple possible field names for status
            status = (
                data.get("status")
                or data.get("state")
                or data.get("data", {}).get("status")
                or ""
            )
            if isinstance(status, str):
                status = status.lower()

            logger.info(f"Revid.ai job {job_id}: status={status!r}")

            if status in ("completed", "done", "finished", "success", "ready"):
                # Try multiple possible field names for the video URL
                video_url = (
                    data.get("url")
                    or data.get("videoUrl")
                    or data.get("video_url")
                    or data.get("outputUrl")
                    or data.get("output_url")
                    or data.get("downloadUrl")
                    or data.get("download_url")
                    or data.get("result", {}).get("url")
                    or data.get("output", {}).get("url")
                    or data.get("data", {}).get("url")
                    or data.get("data", {}).get("videoUrl")
                    or data.get("data", {}).get("outputUrl")
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
                    or f"Unknown error. Full response: {data}"
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

        logger.info(f"Downloaded Revid.ai video -> {output_path}")
        return output_path

    async def create_and_download(
        self,
        script: str,
        output_path: str | Path,
    ) -> Path:
        """
        End-to-end: submit script -> poll until complete -> download .mp4.
        Returns local path to the downloaded video.
        """
        job_id = await self.create_video(script)
        video_url = await self.poll_until_complete(job_id)
        return await self.download_video(video_url, output_path)
