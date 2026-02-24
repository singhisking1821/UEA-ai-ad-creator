"""
B-roll Agent: downloads stock video clips from Pexels for each script's B-roll cues.
Also handles timing calculation based on script word count.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from agents.script_writer import AdScript
from services.pexels import PexelsClient
from utils.logger import logger
import config


def estimate_timings(script: AdScript) -> list[dict]:
    """
    Converts script broll_cues (which have start_second/end_second) into
    a list of {query, start, end} dicts ready for the video editor.
    If the cue already has start_second/end_second, use them.
    Otherwise, distribute evenly.
    """
    cues = script.broll_cues
    total_duration = script.estimated_duration_seconds

    result = []
    for cue in cues:
        if "start_second" in cue and "end_second" in cue:
            result.append({
                "query": cue["query"],
                "start": float(cue["start_second"]),
                "end": float(cue["end_second"]),
                "description": cue.get("description", ""),
            })
        else:
            # Fallback: evenly space B-roll in the middle of the video
            pass

    if not result and cues:
        # Auto-distribute across the video body (skip first 5s hook and last 8s CTA)
        body_start = 5
        body_end = total_duration - 8
        body_duration = max(body_end - body_start, 10)
        segment_dur = body_duration / len(cues)

        for i, cue in enumerate(cues):
            start = body_start + i * segment_dur
            end = min(start + segment_dur - 1, body_end)
            result.append({
                "query": cue["query"],
                "start": round(start, 1),
                "end": round(end, 1),
                "description": cue.get("description", ""),
            })

    return result


async def fetch_broll_for_script(
    script: AdScript,
    temp_dir: Path,
    progress_cb=None,
) -> list[dict]:
    """
    Downloads B-roll clips for a single script.
    Returns list of {path, start, end} dicts.
    """
    script_temp = temp_dir / f"broll_ad_{script.number:02d}"
    script_temp.mkdir(parents=True, exist_ok=True)

    segments = estimate_timings(script)
    if not segments:
        logger.warning(f"Script #{script.number} has no B-roll cues")
        return []

    logger.info(f"Fetching {len(segments)} B-roll clips for Ad #{script.number}")
    if progress_cb:
        progress_cb(f"🎥 Fetching B-roll for Ad #{script.number} ({len(segments)} clips)")

    client = PexelsClient()

    async def fetch_one(seg: dict, idx: int) -> Optional[dict]:
        out = script_temp / f"clip_{idx:02d}.mp4"
        # Try primary query, fallback to a simpler generic query
        path = await client.search_and_download(seg["query"], out)
        if not path:
            fallback_query = " ".join(seg["query"].split()[:2])  # Simpler query
            logger.info(f"Retrying B-roll with simpler query: '{fallback_query}'")
            path = await client.search_and_download(fallback_query, out)
        if path:
            return {"path": str(path), "start": seg["start"], "end": seg["end"]}
        return None

    tasks = [fetch_one(seg, i) for i, seg in enumerate(segments)]
    results = await asyncio.gather(*tasks)
    found = [r for r in results if r is not None]
    logger.info(f"Got {len(found)}/{len(segments)} B-roll clips for Ad #{script.number}")
    return found


async def fetch_broll_for_all_scripts(
    scripts: list[AdScript],
    temp_dir: Path,
    progress_cb=None,
) -> dict[int, list[dict]]:
    """
    Downloads B-roll for all scripts in parallel.
    Returns {script_number: [broll_segments]}.
    """
    results: dict[int, list[dict]] = {}

    async def _one(script: AdScript):
        clips = await fetch_broll_for_script(script, temp_dir, progress_cb)
        results[script.number] = clips

    await asyncio.gather(*[_one(s) for s in scripts])
    return results
