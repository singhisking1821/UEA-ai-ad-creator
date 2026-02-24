"""
Google Sheets client: append ad records to the tracking spreadsheet.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config
from utils.logger import logger

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

SHEET_RANGE = "Ads!A:Z"  # Append to the 'Ads' tab; will be created if doesn't exist


def _get_credentials():
    from pathlib import Path
    creds_path = Path(config.GOOGLE_CREDENTIALS_PATH)
    if not creds_path.exists():
        raise FileNotFoundError(f"Google credentials not found: {creds_path}")
    return service_account.Credentials.from_service_account_file(
        str(creds_path), scopes=SCOPES
    )


class GoogleSheetsClient:
    def __init__(self):
        creds = _get_credentials()
        self.service = build("sheets", "v4", credentials=creds)
        self.sheet_id = config.GOOGLE_SHEET_ID

    def ensure_header(self) -> None:
        """Adds a header row if the sheet is empty."""
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.sheet_id, range="Ads!A1:Z1")
            .execute()
        )
        rows = result.get("values", [])
        if not rows:
            header = [
                "Date", "Ad #", "Website", "Ad Type", "Script Preview",
                "Drive Link", "Status",
            ]
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range="Ads!A1",
                valueInputOption="RAW",
                body={"values": [header]},
            ).execute()

    def append_ad_record(
        self,
        website: str,
        ad_number: int,
        ad_type: str,
        script_preview: str,
        drive_link: str,
        status: str = "Ready",
    ) -> None:
        """Appends one row to the Ads sheet."""
        self.ensure_header()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        row = [now, ad_number, website, ad_type, script_preview[:120], drive_link, status]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.sheet_id,
            range=SHEET_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        logger.info(f"Logged ad #{ad_number} to Google Sheets")
