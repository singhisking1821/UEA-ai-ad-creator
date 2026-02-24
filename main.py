"""
AI Ad Creator — Entry Point

Usage:
  python main.py           # Start the Telegram bot
  python main.py --setup   # Run the API key setup wizard (local only)
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from rich.console import Console

console = Console()


def is_interactive() -> bool:
    """Returns True if running in a real terminal (local), False on cloud servers."""
    return sys.stdin.isatty()


def check_ffmpeg() -> bool:
    """Checks that ffmpeg and ffprobe are available on PATH."""
    import subprocess
    for tool in ["ffmpeg", "ffprobe"]:
        try:
            subprocess.run([tool, "-version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    return True


def check_and_report_missing_keys(cfg) -> bool:
    """
    Checks for missing required env vars.
    - On cloud (non-interactive): prints a clear list of what's missing and exits.
    - On local (interactive): runs the setup wizard to collect them interactively.
    Returns True if all keys are present, False if still missing after wizard.
    """
    if cfg.validate_config():
        return True

    missing = [k["key"] for k in cfg.REQUIRED_KEYS if not __import__("os").getenv(k["key"])]

    if not is_interactive():
        # Running on Railway/cloud — cannot ask for input, just report and exit
        console.print("\n[red bold]❌ Missing required environment variables![/red bold]")
        console.print(
            "[yellow]Add these in Railway → your service → Variables tab:[/yellow]\n"
        )
        for key in missing:
            console.print(f"  [red]•[/red] {key}")
        console.print(
            "\n[dim]See the README for what each variable is and where to get it.[/dim]\n"
        )
        return False
    else:
        # Running locally — run the interactive wizard
        console.print("[yellow]Some API keys are missing. Running setup wizard...[/yellow]\n")
        cfg.run_setup_wizard()
        import importlib
        importlib.reload(cfg)
        return cfg.validate_config()


async def main() -> None:
    parser = argparse.ArgumentParser(description="AI Ad Creator")
    parser.add_argument("--setup", action="store_true", help="Run API key setup wizard")
    args = parser.parse_args()

    # ── Setup wizard (local only) ─────────────────────────────────────────────
    if args.setup:
        if not is_interactive():
            console.print("[red]--setup can only be run locally, not on a cloud server.[/red]")
            sys.exit(1)
        from config import run_setup_wizard
        run_setup_wizard()
        return

    # ── Check FFmpeg ──────────────────────────────────────────────────────────
    if not check_ffmpeg():
        console.print(
            "[red]❌ FFmpeg not found![/red]\n"
            "Install it:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg\n"
            "  Docker: already included in the Dockerfile"
        )
        sys.exit(1)

    # ── Check API keys ────────────────────────────────────────────────────────
    import config as cfg
    if not check_and_report_missing_keys(cfg):
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
