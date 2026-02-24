"""
Central configuration with API key validation and setup wizard.
On first run, missing keys are prompted interactively.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv, set_key

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)


# ─── Required keys and their metadata ────────────────────────────────────────
REQUIRED_KEYS: list[dict] = [
    {
        "key": "TELEGRAM_BOT_TOKEN",
        "label": "Telegram Bot Token",
        "hint": "Get from @BotFather on Telegram → /newbot",
        "required": True,
    },
    {
        "key": "ANTHROPIC_API_KEY",
        "label": "Anthropic API Key (Claude)",
        "hint": "Get from https://console.anthropic.com",
        "required": True,
    },
    {
        "key": "OPENAI_API_KEY",
        "label": "OpenAI API Key (for Whisper subtitles)",
        "hint": "Get from https://platform.openai.com",
        "required": True,
    },
    {
        "key": "HEYGEN_API_KEY",
        "label": "HeyGen API Key (AI Avatar videos)",
        "hint": "Get from https://app.heygen.com/settings → API",
        "required": True,
    },
    {
        "key": "PEXELS_API_KEY",
        "label": "Pexels API Key (free stock B-roll)",
        "hint": "Get from https://www.pexels.com/api/ — it's free",
        "required": True,
    },
    {
        "key": "TAVILY_API_KEY",
        "label": "Tavily API Key (web research)",
        "hint": "Get from https://tavily.com — free tier available",
        "required": True,
    },
    {
        "key": "GOOGLE_CREDENTIALS_PATH",
        "label": "Google Service Account credentials JSON path",
        "hint": "See README for how to create this. Default: google_credentials.json",
        "required": True,
        "default": "google_credentials.json",
    },
    {
        "key": "GOOGLE_DRIVE_FOLDER_ID",
        "label": "Google Drive Folder ID for video uploads",
        "hint": "Right-click folder in Drive → Get link → copy ID after /folders/",
        "required": True,
    },
    {
        "key": "GOOGLE_SHEET_ID",
        "label": "Google Sheet ID for ad tracking",
        "hint": "From sheet URL: docs.google.com/spreadsheets/d/{THIS_PART}/",
        "required": True,
    },
]

OPTIONAL_KEYS: list[dict] = [
    {
        "key": "TELEGRAM_ALLOWED_USERS",
        "label": "Allowed Telegram user IDs (comma-separated, blank = anyone)",
        "hint": "Get your user ID by messaging @userinfobot",
        "required": False,
        "default": "",
    },
    {
        "key": "HEYGEN_DEFAULT_AVATAR_ID",
        "label": "HeyGen default avatar ID (blank = auto-select)",
        "required": False,
        "default": "",
    },
    {
        "key": "HEYGEN_DEFAULT_VOICE_ID",
        "label": "HeyGen default voice ID (blank = auto-select)",
        "required": False,
        "default": "",
    },
]


def run_setup_wizard() -> None:
    """Interactive wizard to collect and save missing API keys."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()
    console.print(Panel.fit(
        "[bold cyan]AI Ad Creator — First-time Setup[/bold cyan]\n"
        "I'll walk you through setting up your API keys.\n"
        "All keys are saved to [bold].env[/bold] in this directory.",
        border_style="cyan",
    ))

    missing = [k for k in REQUIRED_KEYS if not os.getenv(k["key"])]
    if not missing:
        console.print("[green]✓ All required keys already configured![/green]")
        return

    console.print(f"\n[yellow]Found {len(missing)} missing required key(s).[/yellow]\n")

    for item in missing:
        console.print(f"[bold]{item['label']}[/bold]")
        if "hint" in item:
            console.print(f"  [dim]{item['hint']}[/dim]")
        value = Prompt.ask(f"  Enter {item['key']}", default=item.get("default", ""))
        if value:
            set_key(str(ENV_PATH), item["key"], value)
            os.environ[item["key"]] = value
        console.print()

    console.print("[green]✓ Setup complete! Keys saved to .env[/green]\n")


def validate_config() -> bool:
    """Returns True if all required keys are present."""
    missing = [k["key"] for k in REQUIRED_KEYS if not os.getenv(k["key"])]
    return len(missing) == 0


# ─── Config values (accessed as module-level constants) ──────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ALLOWED_USERS: list[str] = [
    u.strip() for u in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()
]

ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

HEYGEN_API_KEY: str = os.getenv("HEYGEN_API_KEY", "")
HEYGEN_DEFAULT_AVATAR_ID: str = os.getenv("HEYGEN_DEFAULT_AVATAR_ID", "")
HEYGEN_DEFAULT_VOICE_ID: str = os.getenv("HEYGEN_DEFAULT_VOICE_ID", "")

PEXELS_API_KEY: str = os.getenv("PEXELS_API_KEY", "")
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "google_credentials.json")
GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")

# ── Cloud deployment: write credentials from env var if file doesn't exist ────
# On Railway/Render/etc. you can't upload files, so paste the entire
# google_credentials.json content as the GOOGLE_CREDENTIALS_JSON env variable.
_creds_json_content = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
if _creds_json_content and not Path(GOOGLE_CREDENTIALS_PATH).exists():
    try:
        Path(GOOGLE_CREDENTIALS_PATH).write_text(_creds_json_content)
    except Exception as _e:
        pass  # Will surface as a clear error when Drive/Sheets is actually called

OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "output"))
TEMP_DIR: Path = Path(os.getenv("TEMP_DIR", "temp"))
VIDEO_WIDTH: int = int(os.getenv("VIDEO_WIDTH", "1080"))
VIDEO_HEIGHT: int = int(os.getenv("VIDEO_HEIGHT", "1920"))

# Ensure output dirs exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Claude model to use for all agents
CLAUDE_MODEL: str = "claude-opus-4-6"

# Ad script settings
DEFAULT_AD_DURATION_SECONDS: int = 45  # Target length per ad
DISCLAIMER_DURATION_SECONDS: int = 5
DISCLAIMER_TEXT: str = (
    "Results may vary. This is not financial advice. "
    "Individual results depend on personal circumstances."
)
