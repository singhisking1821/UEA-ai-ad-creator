"""
Avatar & Voice Selector — AI-driven casting for USAEA ads.

Reads HEYGEN_AVATAR_POOL and HEYGEN_VOICE_POOL from config, then uses
Claude Haiku to pick the best-fit avatar and voice for each script.

Selection logic:
  1. Avatar  — Claude Haiku picks from pool based on script tone/trigger
  2. Voice   — gender-filtered pool; Claude Haiku picks if >1 option
  3. Fallback at every step — never raises; returns ("", "") when no pool
     is configured so the caller can use HeyGen's default discovery.

Usage:
    avatar_id, voice_id = await select_avatar_for_script(script)
    if not avatar_id:
        avatar_id, voice_id = await heygen.get_default_avatar_and_voice()
"""
from __future__ import annotations

import re

import anthropic

import config
from agents.usaea_script_agent import USAEAScript
from utils.logger import logger


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a casting director for short-form legal advocacy ads. "
    "Your only job is to pick the single best spokesperson from the list provided. "
    "Consider the script's emotional tone, target demographic, and hook energy. "
    "Reply with ONLY the number of your choice — nothing else, no explanation."
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_script_context(script: USAEAScript) -> str:
    return (
        f"Campaign: USA Employee Advocates — Wrongful Termination\n"
        f"Emotional Trigger: {script.emotional_trigger}\n"
        f"Hook Type: {script.hook_type_number} ({script.hook_type_name})\n"
        f"Director's Note: {script.director_note}\n"
        f"Target Demographic: {script.target_demographic}\n\n"
        f'Hook: "{script.hook_text}"'
    )


def _parse_choice(raw: str, pool_size: int) -> int:
    """
    Extracts the first digit from Claude's reply and validates it against
    the pool size.  Returns a 0-based index, or 0 on any parse failure.
    """
    digits = re.findall(r"\d", raw.strip())
    if not digits:
        return 0
    choice = int(digits[0])
    if choice < 1 or choice > pool_size:
        return 0
    return choice - 1  # convert to 0-based


async def _claude_pick(user_message: str) -> str:
    """Single Claude Haiku call; returns the raw text reply."""
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=10,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text.strip()


# ── Step 1: pick avatar ────────────────────────────────────────────────────────

async def _select_avatar(script: USAEAScript) -> dict | None:
    """
    Returns the chosen avatar dict from HEYGEN_AVATAR_POOL, or None if the
    pool is empty (caller should fall back to HeyGen default discovery).
    """
    pool = config.HEYGEN_AVATAR_POOL
    if not pool:
        logger.warning("HEYGEN_AVATAR_POOL is empty — no avatar env vars found. Falling back to HeyGen defaults.")
        return None
    logger.info(f"Avatar pool has {len(pool)} entries: {[av['avatar_id'][:8] + '…' for av in pool]}")
    if len(pool) == 1:
        logger.info(f"Avatar pool has 1 entry — using it directly for Ad #{script.number}.")
        return pool[0]

    # Use sequential 1-based numbering (NOT config index) so _parse_choice works correctly
    avatar_lines = "\n".join(
        f"[{i + 1}] {av['description']}  (gender: {av['gender'] or 'unspecified'})"
        for i, av in enumerate(pool)
    )
    user_message = (
        f"{_build_script_context(script)}\n\n"
        f"Available avatars:\n{avatar_lines}\n\n"
        "Reply with ONLY a single digit — the number of the avatar that best fits "
        "this script's tone and target audience."
    )

    try:
        raw = await _claude_pick(user_message)
        logger.info(f"Avatar selection Claude raw reply for Ad #{script.number}: {raw!r}")
        idx = _parse_choice(raw, len(pool))
        chosen = pool[idx]
        logger.info(
            f"Avatar selected for Ad #{script.number}: "
            f"pool[{idx}] {chosen['description'][:60]} "
            f"(avatar_id={chosen['avatar_id'][:8]}…)"
        )
        return chosen
    except Exception as e:
        logger.warning(f"Avatar selection Claude call failed (using pool[0]): {e}", exc_info=True)
        return pool[0]


# ── Step 2: pick voice (gender-matched) ───────────────────────────────────────

async def _select_voice(script: USAEAScript, avatar: dict) -> dict | None:
    """
    Returns the chosen voice dict from HEYGEN_VOICE_POOL, preferring voices
    that match the avatar's gender.  Returns None if pool is empty.
    """
    full_pool = config.HEYGEN_VOICE_POOL
    if not full_pool:
        logger.warning("HEYGEN_VOICE_POOL is empty — no voice env vars found. Falling back to HeyGen defaults.")
        return None
    logger.info(f"Voice pool has {len(full_pool)} entries: {[v['voice_id'][:8] + '…' for v in full_pool]}")

    avatar_gender = avatar.get("gender", "")
    if avatar_gender:
        pool = [v for v in full_pool if v.get("gender", "") == avatar_gender]
        if not pool:
            logger.warning(
                f"No {avatar_gender} voices in pool for Ad #{script.number} — "
                "using full pool as fallback."
            )
            pool = full_pool
    else:
        pool = full_pool

    if len(pool) == 1:
        logger.info(f"Voice pool has 1 matching entry — using it for Ad #{script.number}.")
        return pool[0]

    voice_lines = "\n".join(
        f"[{i + 1}] {v['description']}  (gender: {v['gender'] or 'unspecified'})"
        for i, v in enumerate(pool)
    )
    user_message = (
        f"{_build_script_context(script)}\n\n"
        f"The spokesperson is: {avatar['description']}\n\n"
        f"Available voices (same gender, {avatar_gender or 'any'}):\n{voice_lines}\n\n"
        "Reply with ONLY a single digit — the number of the voice that best fits "
        "the script's emotional tone."
    )

    try:
        raw = await _claude_pick(user_message)
        logger.info(f"Voice selection Claude raw reply for Ad #{script.number}: {raw!r}")
        idx = _parse_choice(raw, len(pool))
        chosen = pool[idx]
        logger.info(
            f"Voice selected for Ad #{script.number}: "
            f"pool[{idx}] {chosen['description'][:60]} "
            f"(voice_id={chosen['voice_id'][:8]}…)"
        )
        return chosen
    except Exception as e:
        logger.warning(f"Voice selection Claude call failed (using pool[0]): {e}", exc_info=True)
        return pool[0]


# ── Public API ────────────────────────────────────────────────────────────────

async def select_avatar_for_script(script: USAEAScript) -> tuple[str, str, str]:
    """
    Returns (avatar_id, voice_id, look_id) for the given script.

    look_id is "" when not configured for the chosen avatar.
    If either pool is empty, returns "" for that component so the caller
    can fill in the gap via HeyGen's default discovery.

    Never raises — all errors are logged and produce graceful fallbacks.
    """
    try:
        avatar = await _select_avatar(script)
        avatar_id = avatar["avatar_id"] if avatar else ""
        look_id   = avatar.get("look_id", "") if avatar else ""
        avatar_gender = avatar.get("gender", "") if avatar else ""

        voice = await _select_voice(script, avatar) if avatar else None
        voice_id = voice["voice_id"] if voice else ""

        logger.info(
            f"Ad #{script.number} casting — "
            f"avatar={avatar_id[:8] if avatar_id else 'default'}… "
            f"look={look_id[:8] if look_id else 'none'}… "
            f"voice={voice_id[:8] if voice_id else 'default'}… "
            f"gender={avatar_gender or 'n/a'}"
        )
        return avatar_id, voice_id, look_id

    except Exception as e:
        logger.error(f"select_avatar_for_script failed (returning empty): {e}", exc_info=True)
        return "", "", ""
