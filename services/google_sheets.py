"""
Google Sheets client using gspread.
Two tabs:
  - 'Script Log'  — deduplication log for generated scripts
  - 'Output Log'  — final rendered video metadata
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]

SCRIPT_LOG_TAB = 'Script Log'
OUTPUT_LOG_TAB = 'Output Log'

SCRIPT_LOG_HEADERS = [
    'script_id', 'created_at', 'ad_type', 'state', 'hook', 'body',
    'cta', 'full_script', 'estimated_seconds', 'avatar_key', 'avatar_reasoning', 'status',
]

OUTPUT_LOG_HEADERS = [
    'script_id', 'created_at', 'ad_type', 'state', 'avatar_key',
    'heygen_video_url', 'shotstack_render_url', 'drive_url', 'render_duration_seconds',
]


def _get_client() -> gspread.Client:
    creds_dict = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _ensure_tab(
    spreadsheet: gspread.Spreadsheet,
    tab_name: str,
    headers: list[str],
) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        ws.append_row(headers)
        logger.info(f'Created tab: {tab_name}')
    else:
        existing = ws.row_values(1)
        if not existing:
            ws.append_row(headers)
    return ws


def _sync_get_recent_scripts(limit: int) -> list[dict]:
    gc = _get_client()
    ss = gc.open_by_key(settings.GOOGLE_SHEET_ID)
    ws = _ensure_tab(ss, SCRIPT_LOG_TAB, SCRIPT_LOG_HEADERS)
    rows = ws.get_all_records()
    return rows[-limit:] if len(rows) > limit else rows


def _sync_log_scripts(scripts_data: list[dict]) -> None:
    gc = _get_client()
    ss = gc.open_by_key(settings.GOOGLE_SHEET_ID)
    ws = _ensure_tab(ss, SCRIPT_LOG_TAB, SCRIPT_LOG_HEADERS)
    for s in scripts_data:
        row = [
            s.get('script_id', ''),
            s.get('created_at', datetime.utcnow().isoformat()),
            s.get('ad_type', ''),
            s.get('state', ''),
            s.get('hook', ''),
            s.get('body', ''),
            s.get('cta', ''),
            s.get('full_script', ''),
            s.get('estimated_seconds', 0),
            s.get('avatar_key', ''),
            s.get('avatar_reasoning', ''),
            'generated',
        ]
        ws.append_row(row)
    logger.info(f'Logged {len(scripts_data)} script(s) to Script Log tab')


def _sync_log_output(output_data: dict) -> None:
    gc = _get_client()
    ss = gc.open_by_key(settings.GOOGLE_SHEET_ID)
    ws = _ensure_tab(ss, OUTPUT_LOG_TAB, OUTPUT_LOG_HEADERS)
    row = [
        output_data.get('script_id', ''),
        output_data.get('created_at', datetime.utcnow().isoformat()),
        output_data.get('ad_type', ''),
        output_data.get('state', ''),
        output_data.get('avatar_key', ''),
        output_data.get('heygen_video_url', ''),
        output_data.get('shotstack_render_url', ''),
        output_data.get('drive_url', ''),
        output_data.get('render_duration_seconds', 0),
    ]
    ws.append_row(row)
    logger.info(f"Logged output for script {output_data.get('script_id')} to Output Log tab")


def _sync_get_last_cta_used() -> str:
    gc = _get_client()
    ss = gc.open_by_key(settings.GOOGLE_SHEET_ID)
    try:
        ws = ss.worksheet(SCRIPT_LOG_TAB)
        rows = ws.get_all_records()
        if rows:
            return str(rows[-1].get('cta', ''))
    except gspread.WorksheetNotFound:
        pass
    return ''


# ── Async wrappers ────────────────────────────────────────────────────────────

async def get_recent_scripts(limit: int = 30) -> list[dict]:
    return await asyncio.to_thread(_sync_get_recent_scripts, limit)


async def log_scripts(scripts: list[Any]) -> None:
    scripts_data = [s.model_dump(mode='json') for s in scripts]
    await asyncio.to_thread(_sync_log_scripts, scripts_data)


async def log_output(output: Any) -> None:
    output_data = output.model_dump(mode='json')
    await asyncio.to_thread(_sync_log_output, output_data)


async def get_last_cta_used() -> str:
    return await asyncio.to_thread(_sync_get_last_cta_used)
