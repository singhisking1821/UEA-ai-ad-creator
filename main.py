"""
USAEA Ad Factory — FastAPI entry point.
Handles Telegram webhooks and routes ad production requests to the pipeline.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from config.settings import settings
from orchestrator.pipeline import parse_telegram_prompt, run_pipeline
from utils.logger import get_logger

logger = get_logger(__name__)


# ── Startup: register Telegram webhook ───────────────────────────────────────

async def _register_telegram_webhook() -> None:
    webhook_url = f'{settings.BASE_URL}/webhook/telegram'
    api_url = (
        f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook'
    )
    payload = {
        'url': webhook_url,
        'secret_token': settings.TELEGRAM_WEBHOOK_SECRET,
        'allowed_updates': ['message'],
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(api_url, json=payload)
            data = resp.json()
        if data.get('ok'):
            logger.info(f'Telegram webhook registered: {webhook_url}')
        else:
            logger.warning(f'Telegram webhook registration failed: {data}')
    except Exception as exc:
        logger.warning(f'Could not register Telegram webhook at startup: {exc}')


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await _register_telegram_webhook()
    yield


app = FastAPI(title='USAEA Ad Factory', version='1.0.0', lifespan=lifespan)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get('/health')
async def health() -> dict:
    return {'status': 'ok', 'version': '1.0.0'}


# ── Telegram webhook ──────────────────────────────────────────────────────────

@app.post('/webhook/telegram')
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=''),
) -> JSONResponse:
    """
    Receives Telegram updates.
    Validates the secret token, checks the allowed chat ID,
    then fires the pipeline as a background task and returns 200 immediately.
    """
    # Validate secret token
    if x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail='Invalid secret token')

    body = await request.json()
    message = body.get('message', {})
    chat = message.get('chat', {})
    chat_id = chat.get('id')
    text = message.get('text', '').strip()

    # Validate chat ID
    if chat_id != settings.TELEGRAM_ALLOWED_CHAT_ID:
        logger.warning(f'Rejected message from unauthorized chat_id: {chat_id}')
        return JSONResponse({'ok': True})

    if not text:
        return JSONResponse({'ok': True})

    logger.info(f'Telegram message from chat {chat_id}: {text[:80]}')

    # Parse and launch pipeline in background so we return 200 immediately
    ad_request = await parse_telegram_prompt(text, chat_id)
    asyncio.create_task(run_pipeline(ad_request))

    return JSONResponse({'ok': True})


# ── Utility: manual webhook registration ─────────────────────────────────────

@app.post('/webhook/register')
async def register_webhook() -> dict:
    """Utility endpoint to manually trigger Telegram webhook registration."""
    await _register_telegram_webhook()
    return {'status': 'webhook registration triggered'}
