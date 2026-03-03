"""
Revid.ai Prompt Agent — Claude Sonnet 4.6

Receives the original USAEA ad script and generates a concise Revid.ai / Typeframes
video creation prompt. Typeframes creates short-form videos from text input with
auto-generated visuals, captions, and music.

The prompt should describe the video content clearly so Typeframes can generate
appropriate B-roll visuals, captions, and pacing.
"""
from __future__ import annotations

import anthropic

import config
from agents.usaea_script_agent import USAEAScript
from utils.logger import logger


# ── System Prompt ────────────────────────────────────────────────────────────

REVID_PROMPT_AGENT_SYSTEM_PROMPT = """\
You are an expert short-form video content creator. You receive an ad script for \
a legal advocacy campaign and must write a concise, clear text prompt that will be \
sent to an AI video generation tool (Typeframes/Revid.ai) to create a polished \
20-second TikTok-style video.

The video tool takes TEXT as input and automatically generates:
- Visuals (stock footage, AI-generated imagery)
- Burned-in captions synced to the narration
- Background music and pacing

YOUR JOB: Write the video script/narration text that the tool will use to create \
the video. Include visual direction as brief inline notes.

RULES:
1. Output the spoken narration EXACTLY as written in the script — do not rewrite it
2. Add brief visual cues in [brackets] before each section
3. End with the disclaimer text on screen
4. Keep total output under 200 words
5. Output ONLY the prompt — no preamble, no explanation

FORMAT YOUR OUTPUT LIKE THIS:
[Visual: office/workplace scenes, urgent energy]
{Hook text from script}

[Visual: legal authority imagery, professional setting]
{Body text from script}

[Visual: hopeful, action-oriented imagery]
{CTA text from script}

[Black screen, white text]
{Disclaimer text}
"""


# ── Main Generator ────────────────────────────────────────────────────────────

async def generate_revid_prompt(
    heygen_video_url: str,
    script: USAEAScript,
) -> str:
    """
    Calls Claude Sonnet 4.6 to generate a Typeframes/Revid.ai video prompt.

    Args:
        heygen_video_url: The completed HeyGen talking head video URL (for reference).
        script: The parsed USAEAScript for this ad.

    Returns:
        A text prompt string, ready to send to the Typeframes API.
    """
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    user_message = (
        f"Create a Typeframes video prompt for this ad script.\n\n"
        f"Director's Note: {script.director_note}\n"
        f"Hook Type: {script.hook_type_number} ({script.hook_type_name}) | "
        f"Emotional Trigger: {script.emotional_trigger}\n"
        f"CTA Variant: {script.cta_variant}\n\n"
        f"[HOOK — 3 seconds]\n{script.hook_text}\n\n"
        f"[BODY — 10 seconds]\n{script.body_text}\n\n"
        f"[CTA — 4 seconds]\n{script.cta_text}\n\n"
        f"[DISCLAIMER — 3 seconds, on-screen only]\n"
        f'"{script.disclaimer_text}"'
    )

    logger.info(f"Calling Revid.ai Prompt Agent (claude-sonnet-4-6) for Ad #{script.number}...")

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=REVID_PROMPT_AGENT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    revid_prompt = response.content[0].text.strip()
    logger.info(
        f"Revid.ai prompt generated for Ad #{script.number} "
        f"({len(revid_prompt)} chars)"
    )
    logger.debug(f"Revid.ai prompt:\n{revid_prompt}")

    return revid_prompt
