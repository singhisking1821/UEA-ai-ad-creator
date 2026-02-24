"""
Google Drive client: upload files and return shareable links.
Uses a Service Account (JSON credentials) for authentication.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config
from utils.logger import logger

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _get_credentials():
    creds_path = Path(config.GOOGLE_CREDENTIALS_PATH)
    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials file not found: {creds_path}\n"
            "See README for setup instructions."
        )
    return service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES
    )


class GoogleDriveClient:
    def __init__(self):
        creds = _get_credentials()
        self.service = build("drive", "v3", credentials=creds)

    def upload_video(
        self,
        local_path: str | Path,
        filename: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> str:
        """
        Uploads a video to Google Drive.
        Returns the shareable link (anyone with link can view).
        """
        local_path = Path(local_path)
        filename = filename or local_path.name
        folder_id = folder_id or config.GOOGLE_DRIVE_FOLDER_ID

        file_metadata = {"name": filename}
        if folder_id:
            file_metadata["parents"] = [folder_id]

        media = MediaFileUpload(
            str(local_path),
            mimetype="video/mp4",
            resumable=True,
        )

        logger.info(f"Uploading {filename} to Google Drive...")
        file = (
            self.service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )
        file_id = file.get("id")

        # Make it viewable by anyone with the link
        self.service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        link = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        logger.info(f"Uploaded → {link}")
        return link
