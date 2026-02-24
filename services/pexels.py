"""
Pexels API client for free stock B-roll video search and download.
Docs: https://www.pexels.com/api/documentation/#videos-search
"""
from __future__ import annotations

import asyncio
import random
from pathlib import Path
from typing import Optional

import httpx

import config
from utils.logger import logger

PEXELS_VIDEO_BASE = "https://api.pexels.com/videos"


class PexelsClient:
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or config.PEXELS_API_KEY
        self.headers = {"Authorization": self.api_key}

    async def search_videos(
        self,
        query: str,
        per_page: int = 5,
        orientation: str = "portrait",
        min_duration: int = 5,
        max_duration: int = 30,
    ) -> list[dict]:
        """
        Returns a list of Pexels video result dicts.
        Each has: id, url, duration, video_files (list with width/height/link)
        """
        params = {
            "query": query,
            "per_page": per_page,
            "orientation": orientation,
            "min_duration": min_duration,
            "max_duration": max_duration,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{PEXELS_VIDEO_BASE}/search",
                headers=self.headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("videos", [])

    def _best_file(self, video: dict, target_width: int = 1080) -> Optional[dict]:
        """Picks the best quality video file close to target_width."""
        files = video.get("video_files", [])
        # Filter to portrait or square videos
        candidates = [
            f for f in files
            if f.get("file_type") == "video/mp4" and f.get("width", 0) > 0
        ]
        if not candidates:
            return None
        # Sort by closeness to target width
        candidates.sort(key=lambda f: abs(f.get("width", 0) - target_width))
        return candidates[0]

    async def download_video(self, url: str, output_path: str | Path) -> Path:
        """Downloads a video file to disk."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(output_path, "wb") as f:
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
        logger.info(f"Downloaded Pexels video → {output_path}")
        return output_path

    async def search_and_download(
        self,
        query: str,
        output_path: str | Path,
        per_page: int = 8,
    ) -> Optional[Path]:
        """
        Searches for a B-roll clip matching `query` and downloads the best result.
        Returns local path or None if nothing found.
        """
        videos = await self.search_videos(query, per_page=per_page)
        if not videos:
            logger.warning(f"No Pexels videos found for: '{query}'")
            return None

        # Try a few candidates
        for video in videos[:3]:
            file_info = self._best_file(video)
            if file_info and file_info.get("link"):
                return await self.download_video(file_info["link"], output_path)

        logger.warning(f"No downloadable Pexels video found for: '{query}'")
        return None

    async def fetch_broll_for_segments(
        self,
        segments: list[dict],  # [{"query": str, "start": float, "end": float}, ...]
        temp_dir: str | Path,
    ) -> list[dict]:
        """
        Downloads B-roll for each segment in parallel.
        Returns list of {"path": Path, "start": float, "end": float} for found clips.
        """
        temp_dir = Path(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        async def fetch_one(seg: dict, idx: int) -> Optional[dict]:
            out = temp_dir / f"broll_{idx:02d}.mp4"
            path = await self.search_and_download(seg["query"], out)
            if path:
                return {"path": str(path), "start": seg["start"], "end": seg["end"]}
            return None

        tasks = [fetch_one(seg, i) for i, seg in enumerate(segments)]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
