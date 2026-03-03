"""
Orchestrator Agent: the brain of the system.

Routes incoming requests to either:
  - USAEA pipeline (for "create two ads for US employee advocates" triggers)
  - Generic pipeline (for "Create N ads for website.com" triggers)

USAEA pipeline (VideoToolAgent_SystemPrompt_v3.pdf):
  Claude Scripting Agent → HeyGen → Revid.ai Prompt Agent → Revid.ai → Drive

Generic pipeline:
  Research → Script Writing → Avatar Video → B-roll → FFmpeg Edit → QC → Drive
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import config
from agents import researcher, script_writer, video_generator, broll_agent, video_editor
from agents import quality_checker, uploader
from agents.usaea_orchestrator import is_usaea_trigger, run_usaea_job, USAEAJob
from utils.logger import logger


# ── Job Dataclass ─────────────────────────────────────────────────────────────

@dataclass
class AdJob:
    """Represents a single ad creation request."""
    job_id: str
    website: str
    num_ads: int
    ad_type: str = "full_broll"   # "full_broll" or "talking_head"
    avatar_id: Optional[str] = None
    voice_id: Optional[str] = None


@dataclass
class JobResult:
    job_id: str
    website: str
    num_requested: int
    num_completed: int
    drive_links: dict[int, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0


# ── Request Parser ─────────────────────────────────────────────────────────────

def parse_request(text: str) -> Optional[AdJob]:
    """
    Parses a natural language Telegram message into an AdJob.

    USAEA triggers (e.g. "create two ads for US employee advocates") are
    detected first and returned as AdJob(ad_type="usaea", num_ads=2).
    The generic pipeline handles all other website-based ad requests.

    Returns None if the message isn't a valid ad creation request.
    """
    text_lower = text.lower().strip()

    # ── USAEA trigger (highest priority) ──────────────────────────────────────
    if is_usaea_trigger(text):
        import uuid
        return AdJob(
            job_id=str(uuid.uuid4())[:8],
            website="usaemployeeadvocates.com",
            num_ads=2,
            ad_type="usaea",
        )

    # ── Generic pipeline ──────────────────────────────────────────────────────
    # Check for trigger words
    if not any(w in text_lower for w in ["create", "make", "generate", "build"]):
        return None
    if "ad" not in text_lower:
        return None

    # Extract number of ads
    num_match = re.search(r"\b(\d+)\b", text)
    num_ads = int(num_match.group(1)) if num_match else 1
    num_ads = max(1, min(num_ads, 10))  # Cap at 10

    # Extract URL
    url_match = re.search(
        r"(https?://[^\s]+|[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)",
        text,
    )
    if not url_match:
        return None
    website = url_match.group(0)
    if not website.startswith("http"):
        website = "https://" + website

    # Detect ad type
    if "talking head" in text_lower or "talking_head" in text_lower:
        ad_type = "talking_head"
    elif "full" in text_lower and ("broll" in text_lower or "b-roll" in text_lower or "b roll" in text_lower):
        ad_type = "full_broll"
    else:
        ad_type = "full_broll"  # Default

    import uuid
    job_id = str(uuid.uuid4())[:8]

    return AdJob(
        job_id=job_id,
        website=website,
        num_ads=num_ads,
        ad_type=ad_type,
    )


# ── Main Orchestrator ─────────────────────────────────────────────────────────

async def run_job(
    job: AdJob,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> JobResult:
    """
    Executes the ad creation pipeline for a job.

    - USAEA jobs (ad_type="usaea") are routed to the USAEA pipeline.
    - All other jobs go through the generic research → script → HeyGen → FFmpeg pipeline.

    progress_cb is called with status update strings throughout.
    """
    # ── Route USAEA jobs ──────────────────────────────────────────────────────
    if job.ad_type == "usaea":
        usaea_job = USAEAJob(job_id=job.job_id)
        usaea_result = await run_usaea_job(usaea_job, progress_cb=progress_cb)
        # Wrap into a JobResult so the Telegram bot handler stays unchanged
        jr = JobResult(
            job_id=job.job_id,
            website=job.website,
            num_requested=2,
            num_completed=len(usaea_result.drive_links),
            drive_links=usaea_result.drive_links,
            errors=usaea_result.errors,
            duration_seconds=usaea_result.duration_seconds,
        )
        return jr

    # ── Generic pipeline ──────────────────────────────────────────────────────
    start_time = time.time()
    result = JobResult(
        job_id=job.job_id,
        website=job.website,
        num_requested=job.num_ads,
        num_completed=0,
    )

    def notify(msg: str):
        logger.info(msg)
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    notify(
        f"🚀 Starting job #{job.job_id}\n"
        f"📍 Website: {job.website}\n"
        f"🎬 Ads: {job.num_ads} × {job.ad_type.replace('_', ' ')}"
    )

    # Set up working directories
    job_dir = config.TEMP_DIR / f"job_{job.job_id}"
    avatar_dir = job_dir / "avatars"
    broll_dir = job_dir / "broll"
    edit_dir = job_dir / "edits"
    output_dir = config.OUTPUT_DIR / f"job_{job.job_id}"

    for d in [job_dir, avatar_dir, broll_dir, edit_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # ── STEP 1: Research ───────────────────────────────────────────────────────
    notify("🔍 Step 1/6: Researching your website...")
    try:
        brief = await researcher.research_website(job.website)
        notify(f"✅ Research complete: {brief.get('company_name', job.website)}")
        notify(f"   Offer: {brief.get('offer_summary', '')[:80]}")
    except Exception as e:
        logger.error(f"Research failed: {e}")
        result.errors.append(f"Research failed: {e}")
        notify(f"⚠️ Research failed ({e}), continuing with defaults...")
        brief = {
            "company_name": job.website,
            "offer_summary": "Employee benefits services",
            "target_audience": "Employees and businesses",
            "pain_points": ["high expenses", "complex benefits", "lack of savings"],
            "key_benefits": ["save money", "easy process", "expert support"],
            "social_proof": [],
            "cta_suggestion": "Click to learn more",
            "unique_mechanism": "IRS-approved benefit plans",
            "ad_angle_ideas": [],
        }

    # ── STEP 2: Script Writing ─────────────────────────────────────────────────
    notify(f"✍️ Step 2/6: Writing {job.num_ads} ad script(s)...")
    try:
        scripts = await script_writer.generate_scripts(
            brief=brief,
            num_ads=job.num_ads,
            ad_type=job.ad_type,
        )
        notify(f"✅ {len(scripts)} scripts ready")
        for s in scripts:
            notify(f"   Ad #{s.number}: {s.angle[:60]}")
    except Exception as e:
        logger.error(f"Script writing failed: {e}")
        result.errors.append(f"Script writing failed: {e}")
        notify("❌ Script writing failed. Aborting.")
        result.duration_seconds = time.time() - start_time
        return result

    # ── STEP 3: Avatar Video Generation ───────────────────────────────────────
    notify(f"🎭 Step 3/6: Generating {len(scripts)} avatar video(s) (takes 5–15 min)...")
    try:
        avatar_paths = await video_generator.generate_all_avatar_videos(
            scripts=scripts,
            output_dir=avatar_dir,
            avatar_id=job.avatar_id,
            voice_id=job.voice_id,
            progress_cb=notify,
            max_concurrent=2,
        )
        notify(f"✅ {len(avatar_paths)}/{len(scripts)} avatar videos generated")
    except Exception as e:
        logger.error(f"Avatar generation failed: {e}")
        result.errors.append(f"Avatar generation failed: {e}")
        notify("❌ Avatar generation failed. Aborting.")
        result.duration_seconds = time.time() - start_time
        return result

    if not avatar_paths:
        notify("❌ No avatar videos generated. Check HeyGen API key and credits.")
        result.duration_seconds = time.time() - start_time
        return result

    # Only continue with scripts that have avatar videos
    successful_scripts = [s for s in scripts if s.number in avatar_paths]

    # ── STEP 4: B-roll Fetching ───────────────────────────────────────────────
    notify(f"📹 Step 4/6: Fetching B-roll clips from Pexels...")
    try:
        broll_clips = await broll_agent.fetch_broll_for_all_scripts(
            scripts=successful_scripts,
            temp_dir=broll_dir,
            progress_cb=notify,
        )
        total_clips = sum(len(v) for v in broll_clips.values())
        notify(f"✅ B-roll ready: {total_clips} clips across {len(broll_clips)} ads")
    except Exception as e:
        logger.error(f"B-roll fetching failed: {e}")
        result.errors.append(f"B-roll fetch failed: {e}")
        broll_clips = {s.number: [] for s in successful_scripts}
        notify("⚠️ B-roll fetch failed, continuing without B-roll")

    # ── STEP 5: Video Editing ─────────────────────────────────────────────────
    notify(f"🎞️ Step 5/6: Editing {len(successful_scripts)} video(s)...")
    try:
        final_videos = await video_editor.edit_all_ads(
            scripts=successful_scripts,
            avatar_paths=avatar_paths,
            broll_clips=broll_clips,
            output_dir=output_dir,
            temp_dir=edit_dir,
            progress_cb=notify,
            max_concurrent=2,
        )
        notify(f"✅ {len(final_videos)}/{len(successful_scripts)} videos edited")
    except Exception as e:
        logger.error(f"Video editing failed: {e}")
        result.errors.append(f"Video editing failed: {e}")
        notify("❌ Video editing failed. Aborting.")
        result.duration_seconds = time.time() - start_time
        return result

    if not final_videos:
        notify("❌ No videos were successfully edited.")
        result.duration_seconds = time.time() - start_time
        return result

    # ── STEP 6: QC ────────────────────────────────────────────────────────────
    notify("🔎 Step 6/7: Running quality checks...")
    qc_results = quality_checker.check_all_ads(final_videos)
    qc_report = quality_checker.format_qc_report(qc_results)
    notify(qc_report)

    # ── STEP 7: Upload ────────────────────────────────────────────────────────
    notify("☁️ Step 7/7: Uploading to Google Drive...")
    try:
        drive_links = await uploader.upload_all_ads(
            scripts=successful_scripts,
            final_videos=final_videos,
            qc_results=qc_results,
            website=job.website,
            progress_cb=notify,
        )
        result.drive_links = drive_links
        result.num_completed = len(drive_links)
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        result.errors.append(f"Upload failed: {e}")
        notify(f"⚠️ Upload failed: {e}")

    result.duration_seconds = time.time() - start_time
    elapsed = int(result.duration_seconds // 60)

    # ── Final Summary ──────────────────────────────────────────────────────────
    summary_lines = [
        f"\n🎉 *Job #{job.job_id} Complete!*",
        f"✅ {result.num_completed}/{job.num_ads} ads created in {elapsed} min",
        "",
        "*Drive Links:*",
    ]
    for num, link in sorted(result.drive_links.items()):
        script = next((s for s in scripts if s.number == num), None)
        angle = script.angle[:40] if script else ""
        summary_lines.append(f"• Ad #{num} ({angle}): {link}")

    if result.errors:
        summary_lines.append(f"\n⚠️ *{len(result.errors)} issue(s):*")
        for err in result.errors[:3]:
            summary_lines.append(f"• {err[:80]}")

    summary_lines.append(
        f"\n📊 All links logged to your Google Sheet."
    )

    notify("\n".join(summary_lines))
    return result
