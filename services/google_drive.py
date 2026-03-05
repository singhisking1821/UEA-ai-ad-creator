"""
Google Drive client — download MP4 from a URL and upload to Drive folder.
Returns a shareable Drive link.
"""
from __future__ import annotations

import asyncio
import io
import json

import httpx
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

SCOPES = ['https://www.googleapis.com/auth/drive.file']


def _get_drive_service():
    creds_dict = json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return build('drive', 'v3', credentials=creds)


def _sync_upload(mp4_bytes: bytes, filename: str) -> str:
    service = _get_drive_service()
    file_metadata = {
        'name': filename,
        'parents': [settings.GOOGLE_DRIVE_FOLDER_ID],
    }
    media = MediaIoBaseUpload(
        io.BytesIO(mp4_bytes),
        mimetype='video/mp4',
        resumable=True,
    )
    logger.info(f'Uploading {filename} to Google Drive...')
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields='id')
        .execute()
    )
    file_id = file.get('id')
    service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'},
    ).execute()
    link = f'https://drive.google.com/file/d/{file_id}/view?usp=sharing'
    logger.info(f'Uploaded to Drive: {link}')
    return link


async def upload_video(mp4_url: str, filename: str) -> str:
    """
    Downloads the MP4 from mp4_url, uploads to Google Drive folder,
    and returns a shareable Drive URL.
    """
    logger.info(f'Downloading MP4 from: {mp4_url}')
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        resp = await client.get(mp4_url)
        resp.raise_for_status()
        mp4_bytes = resp.content

    logger.info(f'Downloaded {len(mp4_bytes)} bytes — uploading to Drive as {filename}')
    return await asyncio.to_thread(_sync_upload, mp4_bytes, filename)
