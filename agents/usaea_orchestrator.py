"""
USAEA Orchestrator — Full 8-Step Pipeline for USA Employee Advocates

Implements VideoToolAgent_SystemPrompt_v3.pdf pipeline:

  Step 1: Read Google Sheets Script_History (last 20 rows)
  Step 2: Claude Scripting Agent → 2 unique 20-second scripts
  Step 3: Log scripts to Google Sheets Script_History tab
  Step 4: HeyGen → 2 talking head videos (webhook or polling)
  Step 5: Claude Revid.ai Prompt Agent → 2 Revid.ai edit prompts
  Step 6: Revid.ai → 2 final 20-second edited videos
  Step 7: Upload to Google Drive (USAEA_WrongfulTermination_YYYYMMDD_AdN.mp4)
  Step 8: Log to Google Sheets Ads tab + send Telegram summary

Trigger keywords (any of):
  "create two ads for US employee advocates"
  "generate ads" / "new scripts" / "make two ads"
  any message with: ads + employee, scripts + USAEA, generate + advocates
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import config
from agents.usaea_script_agent import USAEAScript, generate_usaea_scripts
from agents.revid_prompt_agent import generate_revid_prompt
from services.heygen import HeyGenClient
from services.revid import RevidClient
from services.google_drive import GoogleDriveClient
from services.google_sheets import GoogleSheetsClient
from utils.logger import logger


# ── Job / Result Dataclasses ──────────────────────────────────────────────────

@dataclass
class USAEAJob:
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class USAEAJobResult:
    job_id: str
    scripts: list[USAEAScript] = field(default_factory=list)
    drive_links: dict[int, str] = field(default_factory=dict)   # {ad_number: drive_link}
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0


# ── Trigger Detection ─────────────────────────────────────────────────────────

def is_usaea_trigger(text: str) -> bool:
    """
    Returns True if the message is a USAEA ad creation request.

    Matches trigger patterns from Section 4.4 of the spec:
      "create two ads for US employee advocates"
      "generate ads" / "new scripts" / "make two ads"
      any message with: ads + employee, scripts + USAEA, generate + advocates
    """
    t = text.lower().strip()

    # Exact / near-exact phrases
    exact_triggers = [
        "create two ads for us employee advocates",
        "make two ads for us employee advocates",
        "generate ads for us employee advocates",
        "new scripts for us employee advocates",
        "create ads for usaea",
        "make ads for usaea",
        "generate ads for usaea",
        "create two ads",
        "make two ads",
        "new scripts",
        "generate ads",
    ]
    if any(trigger in t for trigger in exact_triggers):
        return True

    # Combination patterns
    has_create = any(w in t for w in ["create", "make", "generate", "build", "new"])
    has_ad_ref = any(w in t for w in ["ad", "ads", "script", "scripts"])
    has_usaea = any(w in t for w in ["employee", "advocate", "usaea", "wrongful", "termination"])

    return has_create and has_ad_ref and has_usaea


# ── Main Pipeline ─────────────────────────────────────────────────────────────

async def run_usaea_job(
    job: USAEAJob,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> USAEAJobResult:
    """
    Executes the full USAEA ad creation pipeline.

    Args:
        job: A USAEAJob instance (contains only a job_id).
        progress_cb: Optional callable(str) for real-time Telegram status updates.

    Returns:
        USAEAJobResult with drive_links and any errors.
    """
    start_time = time.time()
    result = USAEAJobResult(job_id=job.job_id)

    def notify(msg: str) -> None:
        logger.info(msg)
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    notify(
        f"🚀 USAEA Job #{job.job_id} started\n"
        f"📋 Campaign: Wrongful Termination — Strongfield\n"
        f"🤖 AI Model: claude-sonnet-4-6\n"
        f"🎬 Generating 2 unique 20-second ads..."
    )

    # Working directories
    job_dir    = config.TEMP_DIR   / f"usaea_{job.job_id}"
    output_dir = config.OUTPUT_DIR / f"usaea_{job.job_id}"
    for d in [job_dir, output_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # ── STEP 1: Read Script History ───────────────────────────────────────────
    notify("📊 Step 1/6: Reading Script History Log from Google Sheets...")
    history_block = ""
    try:
        sheets = GoogleSheetsClient()
        history_rows = await asyncio.to_thread(sheets.get_script_history, 20)
        if history_rows:
            history_block = "\n".join(
                f"- {row['date']}: Hook Type {row['hook_type']} / {row['trigger']}"
                for row in history_rows
            )
            notify(f"   Found {len(history_rows)} previous script(s) in history — will avoid repeating.")
        else:
            notify("   No previous scripts found — this is the first run.")
    except Exception as e:
        logger.warning(f"Script history read failed (non-fatal): {e}")
        notify(f"⚠️ Could not read history (non-fatal, continuing): {e}")

    # ── STEP 2: Generate Scripts ──────────────────────────────────────────────
    notify("✍️ Step 2/6: Calling USAEA Scripting Agent (claude-sonnet-4-6)...")
    try:
        scripts = await generate_usaea_scripts(history_block)
        result.scripts = scripts
        for s in scripts:
            notify(
                f"   ✅ Ad #{s.number}: [{s.hook_type_name}] Trigger: {s.emotional_trigger} | "
                f"CTA: {s.cta_variant}\n"
                f"      Hook: \"{s.hook_text}\""
            )
    except Exception as e:
        logger.error(f"Script generation failed: {e}", exc_info=True)
        result.errors.append(f"Script generation failed: {e}")
        notify(f"❌ Script generation failed: {e}")
        result.duration_seconds = time.time() - start_time
        return result

    # ── STEP 3: Log Scripts to Google Sheets ─────────────────────────────────
    notify("📊 Step 3/6: Logging scripts to Script_History tab...")
    try:
        sheets = GoogleSheetsClient()
        for s in scripts:
            await asyncio.to_thread(
                sheets.log_script_history,
                hook_type=f"{s.hook_type_number} ({s.hook_type_name})",
                trigger=s.emotional_trigger,
                cta_variant=s.cta_variant,
                hook_first_words=" ".join(s.hook_text.split()[:8]),
                session_id=job.job_id,
                word_count=s.word_count_total,
            )
        notify(f"   ✅ {len(scripts)} script(s) logged to Script_History.")
    except Exception as e:
        logger.warning(f"Script history write failed (non-fatal): {e}")
        notify(f"⚠️ Script_History logging failed (non-fatal): {e}")

    # ── STEP 4: HeyGen Talking Head Videos ───────────────────────────────────
    notify("🎭 Step 4/6: Submitting scripts to HeyGen (AI talking head)...")
    heygen = HeyGenClient()

    try:
        avatar_id, voice_id = await heygen.get_default_avatar_and_voice()
    except Exception as e:
        logger.error(f"HeyGen avatar/voice lookup failed: {e}")
        result.errors.append(f"HeyGen setup failed: {e}")
        notify(f"❌ HeyGen setup failed: {e}")
        result.duration_seconds = time.time() - start_time
        return result

    async def _generate_heygen(script: USAEAScript) -> tuple[int, str]:
        """Submit one script to HeyGen. Returns (ad_number, heygen_video_url)."""
        notify(f"   🎭 Ad #{script.number}: Submitting {len(script.spoken_text.split())} words to HeyGen...")

        video_id = await heygen.generate_video(
            script=script.spoken_text,
            avatar_id=avatar_id,
            voice_id=voice_id,
            width=1080,
            height=1920,
        )

        notify(f"   ⏳ Ad #{script.number}: HeyGen job {video_id} submitted. Waiting...")

        # Try webhook first if configured, fall back to polling
        webhook_url = getattr(config, "HEYGEN_WEBHOOK_URL", "")
        if webhook_url:
            from services.webhook_server import (
                register_heygen_wait,
                get_heygen_result,
                cleanup_heygen,
            )
            event = register_heygen_wait(video_id)
            try:
                await asyncio.wait_for(event.wait(), timeout=900)   # 15 min max
                payload = get_heygen_result(video_id)
                if payload and payload.get("video_url"):
                    notify(f"   ✅ Ad #{script.number}: HeyGen ready (webhook).")
                    return script.number, payload["video_url"]
                notify(f"   ⚠️ Ad #{script.number}: Webhook had no URL, falling back to polling...")
            except asyncio.TimeoutError:
                notify(f"   ⚠️ Ad #{script.number}: Webhook timeout, falling back to polling...")
            finally:
                cleanup_heygen(video_id)

        # Polling fallback
        heygen_url = await heygen.poll_video_status(video_id)
        notify(f"   ✅ Ad #{script.number}: HeyGen ready (polling).")
        return script.number, heygen_url

    heygen_urls: dict[int, str] = {}
    heygen_tasks = [_generate_heygen(s) for s in scripts]
    heygen_results = await asyncio.gather(*heygen_tasks, return_exceptions=True)
    for res in heygen_results:
        if isinstance(res, Exception):
            logger.error(f"HeyGen video failed: {res}")
            result.errors.append(f"HeyGen failed: {res}")
            notify(f"⚠️ HeyGen failed for one ad: {res}")
        else:
            ad_num, url = res
            heygen_urls[ad_num] = url

    if not heygen_urls:
        notify("❌ No HeyGen videos were generated. Aborting.")
        result.duration_seconds = time.time() - start_time
        return result

    notify(f"   ✅ {len(heygen_urls)}/{len(scripts)} HeyGen talking head videos ready.")

    # ── STEP 5: Revid.ai Prompt Agent + Video Editing ────────────────────────
    notify("🎞️ Step 5/6: Running Revid.ai Prompt Agent + sending to Revid.ai...")
    revid = RevidClient()
    date_str = datetime.now().strftime("%Y%m%d")

    async def _process_revid(script: USAEAScript) -> tuple[int, Path]:
        """Generate Revid prompt, send to Revid.ai, download result."""
        heygen_url = heygen_urls.get(script.number)
        if not heygen_url:
            raise ValueError(f"No HeyGen URL available for Ad #{script.number}")

        notify(f"   🤖 Ad #{script.number}: Generating Revid.ai edit prompt...")
        revid_prompt = await generate_revid_prompt(heygen_url, script)

        notify(f"   🎬 Ad #{script.number}: Sending prompt to Revid.ai API...")
        output_filename = f"USAEA_WrongfulTermination_{date_str}_Ad{script.number}.mp4"
        output_path = output_dir / output_filename

        final_path = await revid.create_and_download(
            revid_prompt=revid_prompt,
            output_path=output_path,
        )

        notify(f"   ✅ Ad #{script.number}: Revid.ai video complete → {final_path.name}")
        return script.number, final_path

    final_videos: dict[int, Path] = {}
    revid_tasks = [
        _process_revid(s)
        for s in scripts
        if s.number in heygen_urls
    ]
    revid_results = await asyncio.gather(*revid_tasks, return_exceptions=True)
    for res in revid_results:
        if isinstance(res, Exception):
            logger.error(f"Revid.ai processing failed: {res}", exc_info=True)
            result.errors.append(f"Revid.ai failed: {res}")
            notify(f"⚠️ Revid.ai failed for one ad: {res}")
        else:
            ad_num, path = res
            final_videos[ad_num] = path

    if not final_videos:
        notify("❌ Revid.ai produced no videos. Aborting.")
        result.duration_seconds = time.time() - start_time
        return result

    notify(f"   ✅ {len(final_videos)}/{len(heygen_urls)} Revid.ai videos ready.")

    # ── STEP 6: Upload to Google Drive + Log to Sheets ────────────────────────
    notify("☁️ Step 6/6: Uploading to Google Drive + logging to Sheets...")
    drive  = GoogleDriveClient()
    sheets = GoogleSheetsClient()

    for ad_num, video_path in sorted(final_videos.items()):
        script = next((s for s in scripts if s.number == ad_num), None)
        try:
            notify(f"   ☁️ Ad #{ad_num}: Uploading {video_path.name} to Google Drive...")
            link = await asyncio.to_thread(drive.upload_video, video_path, video_path.name)
            result.drive_links[ad_num] = link

            if script:
                preview = f"[{script.hook_type_name}] {script.hook_text[:80]}"
                await asyncio.to_thread(
                    sheets.append_ad_record,
                    "usaemployeeadvocates.com",
                    ad_num,
                    "USAEA_WrongfulTermination",
                    preview,
                    link,
                    "Ready",
                )

            notify(f"   ✅ Ad #{ad_num}: {link}")

        except Exception as e:
            logger.error(f"Upload/log failed for Ad #{ad_num}: {e}")
            result.errors.append(f"Upload failed for Ad #{ad_num}: {e}")
            notify(f"⚠️ Upload failed for Ad #{ad_num}: {e}")

    # ── Final Summary ─────────────────────────────────────────────────────────
    result.duration_seconds = time.time() - start_time
    elapsed_min = int(result.duration_seconds // 60)

    lines = [
        f"\n🎉 *USAEA Job #{job.job_id} Complete!*",
        f"✅ {len(result.drive_links)}/{len(scripts)} ads ready in {elapsed_min} min",
        f"📋 Campaign: Wrongful Termination — Strongfield",
        "",
        "*Ad Links:*",
    ]
    for ad_num in sorted(result.drive_links):
        s = next((x for x in scripts if x.number == ad_num), None)
        hook_preview = f' — "{s.hook_text[:50]}"' if s else ""
        lines.append(f"• [Ad #{ad_num}]({result.drive_links[ad_num]}){hook_preview}")

    lines.append("\n📊 Scripts logged to Script\\_History | Videos logged to Ads tab")

    if result.errors:
        lines.append(f"\n⚠️ {len(result.errors)} issue(s) encountered:")
        for err in result.errors[:3]:
            lines.append(f"• {err[:100]}")

    notify("\n".join(lines))
    return result
