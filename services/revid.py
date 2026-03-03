"""
Revid.ai API client.

Revid.ai is an AI-powered video editing and creation platform.
This client sends edit prompts to Revid.ai and polls for the resulting video.

⚠️  IMPORTANT — Before deploying, verify the following against your Revid.ai API docs:
    1. REVID_BASE URL (currently https://api.revid.ai — confirm with Revid.ai support)
    2. Endpoint paths: /v1/video/create and /v1/video/{job_id}/status
    3. Request payload structure (the "prompt" field key)
    4. Response field names for job_id, status, and video_url
    Contact Revid.ai support or check their API documentation for exact details.

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

# ⚠️  Confirm this base URL with Revid.ai. It may be https://api.revid.ai/v1 or similar.
REVID_BASE = "https://api.revid.ai"


class RevidClient:
    """
    Revid.ai API client.

    Typical usage:
        client = RevidClient()
        path = await client.create_and_download(revid_prompt, output_path)

    Or step by step:
        job_id   = await client.create_video(revid_prompt)
        video_url = await client.poll_until_complete(job_id)
        path     = await client.download_video(video_url, output_path)
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or config.REVID_API_KEY
        self.headers = {
            # ⚠️  Revid.ai may use "X-Api-Key" instead of "Authorization: Bearer".
            # Check their API docs and adjust if needed.
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
    async def create_video(self, revid_prompt: str) -> str:
        """
        Submits a video edit job to Revid.ai.
        Returns the job_id string.

        ⚠️  Endpoint: POST /v1/video/create
            Adjust the path and payload keys to match Revid.ai's actual API contract.
        """
        # ⚠️  Adjust payload keys to match what Revid.ai expects.
        payload = {
            "prompt": revid_prompt,
            # Additional fields Revid.ai may require, e.g.:
            # "template_id": "employment_law",
            # "output_format": "mp4",
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{REVID_BASE}/v1/video/create",   # ⚠️ Verify endpoint path
                headers=self.headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        # ⚠️  Adjust key path to match Revid.ai's actual response structure.
        job_id = (
            data.get("job_id")
            or data.get("id")
            or data.get("data", {}).get("job_id")
            or data.get("data", {}).get("id")
        )
        if not job_id:
            raise RuntimeError(
                f"Revid.ai did not return a job_id. Full response: {data}"
            )

        logger.info(f"Revid.ai job submitted: {job_id}")
        return str(job_id)

    async def get_video_status(self, job_id: str) -> dict:
        """
        Returns the current status dict for a Revid.ai job.

        ⚠️  Endpoint: GET /v1/video/{job_id}/status
            Adjust to match Revid.ai's actual polling endpoint path.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{REVID_BASE}/v1/video/{job_id}/status",   # ⚠️ Verify endpoint path
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def poll_until_complete(
        self,
        job_id: str,
        poll_interval: int = 20,
        max_wait_seconds: int = 600,  # 10 minutes
    ) -> str:
        """
        Polls Revid.ai until the video job is complete.
        Returns the video download URL.

        ⚠️  Adjust the status values and response field names to match Revid.ai's API.
            Common patterns for status: "completed" / "done" / "finished" / "success"
            Common patterns for URL key: "video_url" / "output_url" / "url" / "download_url"
        """
        start = time.time()
        while time.time() - start < max_wait_seconds:
            data = await self.get_video_status(job_id)

            # ⚠️  Adjust field names to match Revid.ai's response structure
            status = (
                data.get("status")
                or data.get("data", {}).get("status")
                or ""
            ).lower()

            logger.info(f"Revid.ai job {job_id}: status={status!r}")

            if status in ("completed", "done", "finished", "success"):
                # ⚠️  Adjust field name for the download URL
                video_url = (
                    data.get("video_url")
                    or data.get("output_url")
                    or data.get("url")
                    or data.get("download_url")
                    or data.get("data", {}).get("video_url")
                    or data.get("data", {}).get("output_url")
                    or data.get("data", {}).get("url")
                    or data.get("data", {}).get("download_url")
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
            f"Revid.ai job {job_id} did not complete within {max_wait_seconds}s. "
            "Increase REVID_MAX_WAIT_SECONDS or check your Revid.ai account."
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
        revid_prompt: str,
        output_path: str | Path,
    ) -> Path:
        """
        End-to-end: submit prompt → poll until complete → download .mp4.
        Returns local path to the downloaded video.
        """
        job_id = await self.create_video(revid_prompt)
        video_url = await self.poll_until_complete(job_id)
        return await self.download_video(video_url, output_path)
