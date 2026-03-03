"""
Webhook server for receiving async callbacks from HeyGen.

Uses aiohttp (already in requirements.txt) to run a lightweight HTTP server
alongside the Telegram bot in the same asyncio event loop.

Railway provides a public URL. To enable webhooks:
  1. Deploy to Railway → copy your public domain
     e.g. https://ai-ad-creator.up.railway.app
  2. Add this Railway variable:
     HEYGEN_WEBHOOK_URL = https://ai-ad-creator.up.railway.app/webhook/heygen
  3. Register that URL in your HeyGen dashboard:
     app.heygen.com → Settings → Webhooks → Add endpoint
     Events to subscribe: avatar_video.success, avatar_video.fail

Without HEYGEN_WEBHOOK_URL set, the pipeline automatically falls back to polling.

Endpoints:
    POST /webhook/heygen  — HeyGen notifies when a video is ready
    GET  /health          — Health check (used by Railway to verify the service)
"""
from __future__ import annotations

import asyncio
from typing import Optional

from aiohttp import web

from utils.logger import logger


# ── In-memory state ───────────────────────────────────────────────────────────
# Keyed by video_id

_heygen_events: dict[str, asyncio.Event] = {}
_heygen_results: dict[str, dict] = {}


def register_heygen_wait(video_id: str) -> asyncio.Event:
    """
    Called before submitting a video to HeyGen.
    Creates and stores an asyncio.Event that will be set when the webhook
    arrives for this video_id.  The orchestrator awaits this event.
    """
    event = asyncio.Event()
    _heygen_events[video_id] = event
    return event


def get_heygen_result(video_id: str) -> Optional[dict]:
    """Returns the webhook payload for a completed HeyGen video, or None."""
    return _heygen_results.get(video_id)


def cleanup_heygen(video_id: str) -> None:
    """Cleans up state for a video_id after it has been handled."""
    _heygen_events.pop(video_id, None)
    _heygen_results.pop(video_id, None)


# ── Webhook Handlers ──────────────────────────────────────────────────────────

async def handle_heygen_webhook(request: web.Request) -> web.Response:
    """
    Handles HeyGen webhook POST callbacks.

    HeyGen sends a JSON payload like:
    {
        "event_type": "avatar_video.success",
        "event_data": {
            "video_id": "abc123",
            "video_url": "https://cdn.heygen.com/...",
            "status": "completed"
        }
    }

    ⚠️  Verify the exact field names against HeyGen's webhook documentation:
        https://docs.heygen.com/reference/webhook-events
    """
    try:
        payload = await request.json()
        logger.info(f"HeyGen webhook received: {payload}")

        # ⚠️  Adjust these field paths to match HeyGen's actual webhook format.
        event_data = payload.get("event_data", payload)

        video_id = (
            event_data.get("video_id")
            or payload.get("video_id")
            or ""
        )
        video_url = (
            event_data.get("video_url")
            or event_data.get("url")
            or payload.get("video_url")
            or ""
        )
        status = (
            event_data.get("status")
            or payload.get("status")
            or payload.get("event_type", "")
            or ""
        ).lower()

        if not video_id:
            logger.warning(f"HeyGen webhook: no video_id in payload: {payload}")
            return web.Response(status=400, text="Missing video_id")

        # Store result for the orchestrator to read
        _heygen_results[video_id] = {
            "video_url": video_url,
            "status": status,
            "raw": payload,
        }

        # Unblock the waiting orchestrator coroutine
        event = _heygen_events.get(video_id)
        if event:
            event.set()
            logger.info(f"HeyGen webhook: notified waiter for video_id={video_id}")
        else:
            logger.warning(
                f"HeyGen webhook: no registered waiter for video_id={video_id} "
                "(may have already timed out and fallen back to polling)"
            )

        return web.Response(status=200, text="OK")

    except Exception as e:
        logger.error(f"HeyGen webhook handler error: {e}", exc_info=True)
        return web.Response(status=500, text=str(e))


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint used by Railway to verify the service is alive."""
    return web.Response(text="OK", content_type="text/plain")


# ── App Builder ───────────────────────────────────────────────────────────────

def build_webhook_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webhook/heygen", handle_heygen_webhook)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/", handle_health)   # Root also returns 200 for Railway
    return app


async def start_webhook_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """
    Starts the aiohttp webhook server in the current asyncio event loop.
    Call this as an asyncio background task from main.py.

    Railway sets the PORT environment variable automatically.
    The host/port are read from config (which reads from env).
    """
    app = build_webhook_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"Webhook server listening on http://{host}:{port}")
    logger.info(f"  HeyGen webhook: POST http://{host}:{port}/webhook/heygen")
    logger.info(f"  Health check:   GET  http://{host}:{port}/health")
