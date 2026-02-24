"""
Telegram Bot: the user-facing interface.

Commands:
  /start    — Welcome message and usage instructions
  /status   — Show running jobs
  /avatars  — List available HeyGen avatars
  /help     — Help message

Natural language:
  "Create 5 ads for usaemployeeadvocates.com"
  "Make 3 talking head ads for mysite.com"
"""
from __future__ import annotations

import asyncio
import html
import traceback
from typing import Optional

from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
from agents.orchestrator import parse_request, run_job, AdJob
from services.heygen import HeyGenClient
from utils.logger import logger

# Track running jobs: {chat_id: [job_id, ...]}
_running_jobs: dict[int, list[str]] = {}


# ── Auth Guard ────────────────────────────────────────────────────────────────

def _is_authorized(update: Update) -> bool:
    if not config.TELEGRAM_ALLOWED_USERS:
        return True  # No restriction configured
    user_id = str(update.effective_user.id)
    return user_id in config.TELEGRAM_ALLOWED_USERS


async def _deny(update: Update) -> None:
    await update.message.reply_text(
        "⛔ You are not authorized to use this bot.\n"
        f"Your user ID: `{update.effective_user.id}`\n"
        "Add your ID to TELEGRAM_ALLOWED_USERS in .env",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _deny(update)
        return

    await update.message.reply_text(
        "👋 *AI Ad Creator Bot*\n\n"
        "I create fully-edited Facebook video ads using AI avatars, B-roll, and subtitles.\n\n"
        "*To create ads, just message me:*\n"
        "`Create 5 ads for usaemployeeadvocates.com`\n"
        "`Make 3 talking head ads for mysite.com`\n"
        "`Generate 2 full broll ads for example.com`\n\n"
        "*Options:*\n"
        "• `full broll` (default) — Avatar full screen with B-roll overlaid\n"
        "• `talking head` — Avatar at bottom, B-roll background\n\n"
        "*Other commands:*\n"
        "/avatars — List available HeyGen avatars\n"
        "/status — Show running jobs\n"
        "/help — Show this message\n\n"
        "_Ads are uploaded to Google Drive and logged to your Google Sheet._",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _deny(update)
        return

    chat_id = update.effective_chat.id
    jobs = _running_jobs.get(chat_id, [])
    if jobs:
        await update.message.reply_text(
            f"🔄 *Running jobs:* {', '.join(f'#{j}' for j in jobs)}",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text("✅ No jobs currently running.")


async def cmd_avatars(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _deny(update)
        return

    msg = await update.message.reply_text("⏳ Fetching available HeyGen avatars...")
    try:
        client = HeyGenClient()
        avatars = await client.list_avatars()
        if not avatars:
            await msg.edit_text("No avatars found. Check your HeyGen API key.")
            return

        lines = ["*Available HeyGen Avatars:*\n"]
        for av in avatars[:20]:  # Show max 20
            name = av.get("avatar_name", "Unknown")
            av_id = av.get("avatar_id", "")
            lines.append(f"• `{av_id}` — {name}")

        lines.append(
            "\nTo use a specific avatar, add its ID to .env as HEYGEN_DEFAULT_AVATAR_ID"
        )
        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await msg.edit_text(f"❌ Failed to fetch avatars: {e}")


# ── Main Message Handler ──────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        await _deny(update)
        return

    text = update.message.text or ""
    chat_id = update.effective_chat.id

    # Try to parse as an ad creation request
    job = parse_request(text)
    if not job:
        await update.message.reply_text(
            "I didn't understand that request.\n\n"
            "Try: `Create 5 ads for usaemployeeadvocates.com`\n"
            "Or use /help to see all options.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Acknowledge and start
    ack = await update.message.reply_text(
        f"✅ Got it! Starting job #{job.job_id}\n"
        f"📍 {job.website}\n"
        f"🎬 {job.num_ads} × {job.ad_type.replace('_', ' ')} ads\n\n"
        "I'll send you updates as each step completes. "
        "This typically takes 20–40 minutes for 5 ads.",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Track job
    if chat_id not in _running_jobs:
        _running_jobs[chat_id] = []
    _running_jobs[chat_id].append(job.job_id)

    # Build progress callback that sends Telegram messages
    async def _async_progress(msg: str):
        try:
            # Escape for Markdown
            safe_msg = msg.replace("_", "\\_").replace("*", "")
            if len(safe_msg) > 4000:
                safe_msg = safe_msg[:4000] + "..."
            await context.bot.send_message(
                chat_id=chat_id,
                text=safe_msg,
                parse_mode=ParseMode.MARKDOWN,
                disable_notification=True,
            )
        except Exception as e:
            logger.warning(f"Progress message send failed: {e}")

    def progress_cb(msg: str):
        # Schedule the coroutine in the event loop
        asyncio.create_task(_async_progress(msg))

    # Run the job
    try:
        result = await run_job(job, progress_cb=progress_cb)

        # Send final summary
        if result.drive_links:
            lines = [f"🎉 *Job #{job.job_id} Complete!*\n"]
            lines.append(f"✅ {result.num_completed}/{job.num_ads} ads created\n")
            lines.append("*Your ad links:*")
            for num, link in sorted(result.drive_links.items()):
                lines.append(f"• [Ad #{num}]({link})")
            lines.append("\n📊 All logged to your Google Sheet")
            await context.bot.send_message(
                chat_id=chat_id,
                text="\n".join(lines),
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⚠️ Job #{job.job_id} finished but no ads were uploaded. Check logs.",
            )

    except Exception as e:
        logger.error(f"Job {job.job_id} crashed: {traceback.format_exc()}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Job #{job.job_id} encountered an error:\n`{str(e)[:500]}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    finally:
        if job.job_id in _running_jobs.get(chat_id, []):
            _running_jobs[chat_id].remove(job.job_id)


# ── Error Handler ─────────────────────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Telegram error: {context.error}", exc_info=context.error)


# ── App Builder ───────────────────────────────────────────────────────────────

def build_application() -> Application:
    """Builds and returns the Telegram Application."""
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("avatars", cmd_avatars))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    return app


async def set_bot_commands(app: Application) -> None:
    """Registers bot commands with Telegram for autocomplete."""
    await app.bot.set_my_commands([
        BotCommand("start", "Welcome & usage instructions"),
        BotCommand("help", "Show help"),
        BotCommand("avatars", "List available HeyGen avatars"),
        BotCommand("status", "Show running jobs"),
    ])
