"""
Google Sheets client: append ad records and script history to the tracking spreadsheet.

Two tabs are used:
  Ads            — Final video upload log (existing functionality)
  Script_History — USAEA cross-session uniqueness log (new for USAEA pipeline)
                   Columns: Date | Hook Type | Emotional Trigger | CTA Variant |
                            Hook First Words | Session ID | Word Count
"""
from __future__ import annotations

from datetime import datetime

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config
from utils.logger import logger

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

ADS_RANGE            = "Ads!A:Z"
HISTORY_RANGE        = "Script_History!A:Z"
HISTORY_HEADER_RANGE = "Script_History!A1:G1"


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

    # ── Ads Tab ───────────────────────────────────────────────────────────────

    def ensure_header(self) -> None:
        """Adds a header row to the Ads tab if it is empty."""
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
        """Appends one row to the Ads tab."""
        self.ensure_header()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        row = [now, ad_number, website, ad_type, script_preview[:120], drive_link, status]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.sheet_id,
            range=ADS_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        logger.info(f"Logged ad #{ad_number} to Google Sheets (Ads tab)")

    # ── Script_History Tab (USAEA cross-session uniqueness) ───────────────────

    def _ensure_script_history_header(self) -> None:
        """Adds a header row to the Script_History tab if it is empty."""
        result = (
            self.service.spreadsheets()
            .values()
            .get(spreadsheetId=self.sheet_id, range=HISTORY_HEADER_RANGE)
            .execute()
        )
        rows = result.get("values", [])
        if not rows:
            header = [
                "Date", "Hook Type", "Emotional Trigger", "CTA Variant",
                "Hook First Words", "Session ID", "Word Count",
            ]
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range="Script_History!A1",
                valueInputOption="RAW",
                body={"values": [header]},
            ).execute()
            logger.info("Created Script_History header row in Google Sheets")

    def log_script_history(
        self,
        hook_type: str,
        trigger: str,
        cta_variant: str,
        hook_first_words: str,
        session_id: str,
        word_count: int,
    ) -> None:
        """
        Appends one row to the Script_History tab.
        Called after each USAEA script is generated to prevent cross-session repetition.
        """
        self._ensure_script_history_header()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        row = [now, hook_type, trigger, cta_variant, hook_first_words[:60], session_id, word_count]
        self.service.spreadsheets().values().append(
            spreadsheetId=self.sheet_id,
            range=HISTORY_RANGE,
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]},
        ).execute()
        logger.info(f"Logged to Script_History: {hook_type} / {trigger}")

    def get_script_history(self, limit: int = 20) -> list[dict]:
        """
        Reads the most recent `limit` rows from the Script_History tab.
        Returns a list of dicts with keys:
            date, hook_type, trigger, cta_variant, hook_first_words, session_id, word_count
        Returns [] if the tab is empty or doesn't exist yet.
        """
        try:
            result = (
                self.service.spreadsheets()
                .values()
                .get(spreadsheetId=self.sheet_id, range=HISTORY_RANGE)
                .execute()
            )
        except Exception as e:
            logger.warning(f"Could not read Script_History tab (non-fatal): {e}")
            return []

        rows = result.get("values", [])
        if not rows or len(rows) < 2:
            return []   # Empty or header-only

        # Skip header row; take the last `limit` data rows
        data_rows = rows[1:][-limit:]

        history = []
        for row in data_rows:
            # Pad to 7 columns in case trailing cells are empty
            row = row + [""] * (7 - len(row))
            history.append({
                "date":             row[0],
                "hook_type":        row[1],
                "trigger":          row[2],
                "cta_variant":      row[3],
                "hook_first_words": row[4],
                "session_id":       row[5],
                "word_count":       row[6],
            })

        return history
