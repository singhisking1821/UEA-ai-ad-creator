"""
HeyGen API client for AI avatar video generation.
Docs: https://docs.heygen.com/reference/generate-video-v2
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from utils.logger import logger

HEYGEN_BASE = "https://api.heygen.com"


class HeyGenClient:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or config.HEYGEN_API_KEY
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    # ── Avatar / Voice Discovery ───────────────────────────────────────────────

    async def list_avatars(self) -> list[dict]:
        """Returns list of available avatar dicts."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{HEYGEN_BASE}/v2/avatars", headers=self.headers)
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("avatars", [])

    async def list_voices(self, language: str = "en") -> list[dict]:
        """Returns list of available voice dicts."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{HEYGEN_BASE}/v2/voices",
                headers=self.headers,
                params={"language": language},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", {}).get("voices", [])

    async def get_default_avatar_and_voice(self) -> tuple[str, str]:
        """
        Returns (avatar_id, voice_id).
        Uses env config if set, otherwise picks first available.
        """
        avatar_id = config.HEYGEN_DEFAULT_AVATAR_ID
        voice_id = config.HEYGEN_DEFAULT_VOICE_ID

        if not avatar_id:
            avatars = await self.list_avatars()
            if not avatars:
                raise ValueError("No HeyGen avatars available in your account.")
            # Prefer photorealistic talking head avatars
            avatar_id = avatars[0]["avatar_id"]
            logger.info(f"Auto-selected HeyGen avatar: {avatar_id}")

        if not voice_id:
            voices = await self.list_voices()
            # Prefer English US voices
            en_voices = [v for v in voices if "en-US" in v.get("language", "")]
            pick = en_voices[0] if en_voices else voices[0] if voices else None
            if not pick:
                raise ValueError("No HeyGen voices available.")
            voice_id = pick["voice_id"]
            logger.info(f"Auto-selected HeyGen voice: {voice_id}")

        return avatar_id, voice_id

    # ── Video Generation ───────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
    async def generate_video(
        self,
        script: str,
        avatar_id: Optional[str] = None,
        voice_id: Optional[str] = None,
        width: int = 1080,
        height: int = 1920,
    ) -> str:
        """
        Submits a video generation job to HeyGen.
        Returns the video_id to poll for status.
        """
        if not avatar_id or not voice_id:
            avatar_id, voice_id = await self.get_default_avatar_and_voice()

        payload = {
            "video_inputs": [
                {
                    "character": {
                        "type": "avatar",
                        "avatar_id": avatar_id,
                        "avatar_style": "normal",
                    },
                    "voice": {
                        "type": "text",
                        "input_text": script,
                        "voice_id": voice_id,
                        "speed": 1.0,
                    },
                }
            ],
            "dimension": {"width": width, "height": height},
            "aspect_ratio": None,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{HEYGEN_BASE}/v2/video/generate",
                headers=self.headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        video_id = data.get("data", {}).get("video_id")
        if not video_id:
            raise RuntimeError(f"HeyGen did not return video_id: {data}")
        logger.info(f"HeyGen video job submitted: {video_id}")
        return video_id

    async def poll_video_status(
        self,
        video_id: str,
        poll_interval: int = 15,
        max_wait_seconds: int = 900,  # 15 minutes
    ) -> str:
        """
        Polls HeyGen until the video is complete.
        Returns the download URL.
        """
        start = time.time()
        async with httpx.AsyncClient(timeout=30) as client:
            while time.time() - start < max_wait_seconds:
                resp = await client.get(
                    f"{HEYGEN_BASE}/v1/video_status.get",
                    headers=self.headers,
                    params={"video_id": video_id},
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                status = data.get("status", "")
                logger.info(f"HeyGen video {video_id}: status={status}")

                if status == "completed":
                    url = data.get("video_url")
                    if not url:
                        raise RuntimeError("HeyGen completed but no video_url returned.")
                    return url
                elif status in ("failed", "error"):
                    raise RuntimeError(f"HeyGen video generation failed: {data}")

                await asyncio.sleep(poll_interval)

        raise TimeoutError(f"HeyGen video {video_id} did not complete within {max_wait_seconds}s")

    async def download_video(self, url: str, output_path: str | Path) -> Path:
        """Downloads a video from a URL to disk."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
        logger.info(f"Downloaded HeyGen video → {output_path}")
        return output_path

    async def create_video(
        self,
        script: str,
        output_path: str | Path,
        avatar_id: Optional[str] = None,
        voice_id: Optional[str] = None,
        width: int = 1080,
        height: int = 1920,
    ) -> Path:
        """
        End-to-end: submit → poll → download.
        Returns local path to downloaded video.
        """
        video_id = await self.generate_video(script, avatar_id, voice_id, width, height)
        url = await self.poll_video_status(video_id)
        return await self.download_video(url, output_path)
