"""
AI Ad Creator — Entry Point

Usage:
  python main.py           # Start the Telegram bot
  python main.py --setup   # Run the API key setup wizard only
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console

console = Console()


def check_ffmpeg() -> bool:
    """Checks that ffmpeg and ffprobe are available on PATH."""
    import subprocess
    for tool in ["ffmpeg", "ffprobe"]:
        try:
            subprocess.run([tool, "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(description="AI Ad Creator")
    parser.add_argument("--setup", action="store_true", help="Run API key setup wizard")
    args = parser.parse_args()

    # ── Setup wizard ──────────────────────────────────────────────────────────
    if args.setup:
        from config import run_setup_wizard
        run_setup_wizard()
        return

    # ── Check dependencies ────────────────────────────────────────────────────
    if not check_ffmpeg():
        console.print(
            "[red]❌ FFmpeg not found![/red]\n"
            "Install it:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )
        sys.exit(1)

    # ── First-run setup if keys are missing ───────────────────────────────────
    import config as cfg
    if not cfg.validate_config():
        console.print("[yellow]Some API keys are missing. Running setup wizard...[/yellow]\n")
        cfg.run_setup_wizard()
        # Reload config after setup
        import importlib
        importlib.reload(cfg)

        if not cfg.validate_config():
            console.print(
                "[red]Still missing required keys. "
                "Please fill in the .env file and restart.[/red]"
            )
            sys.exit(1)

    # ── Start Telegram Bot ────────────────────────────────────────────────────
    from bot.telegram_bot import build_application, set_bot_commands

    console.print(
        "[bold green]🚀 AI Ad Creator starting...[/bold green]\n"
        f"Model: [cyan]{cfg.CLAUDE_MODEL}[/cyan]\n"
        f"Output dir: [cyan]{cfg.OUTPUT_DIR}[/cyan]\n"
    )

    app = build_application()

    async with app:
        await set_bot_commands(app)
        console.print("[green]✅ Bot is running. Send a message on Telegram to start![/green]")
        await app.start()
        await app.updater.start_polling(allowed_updates=["message"])

        # Keep running until interrupted
        try:
            await asyncio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            await app.updater.stop()
            await app.stop()

    console.print("[yellow]Bot stopped.[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
