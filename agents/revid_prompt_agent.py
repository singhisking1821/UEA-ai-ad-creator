"""
Revid.ai Prompt Agent — Claude Sonnet 4.6

Receives a completed Heygen talking head video URL and the original USAEA ad script.
Generates a precise Revid.ai edit prompt covering B-roll, captions, pacing, and disclaimer.

System prompt implements the full Section 3 spec from VideoToolAgent_SystemPrompt_v3.pdf
"""
from __future__ import annotations

import anthropic

import config
from agents.usaea_script_agent import USAEAScript
from utils.logger import logger


# ── System Prompt — Full Section 3 from VideoToolAgent_SystemPrompt_v3.pdf ────

REVID_PROMPT_AGENT_SYSTEM_PROMPT = """\
You are an expert Revid.ai video editor agent. You receive a completed Heygen talking head \
video URL and the original ad script. Your job is to write a precise, detailed Revid.ai edit \
prompt that will produce a polished, 20-second final video. You are responsible for B-roll \
selection, caption styling, pacing, and the legal disclaimer overlay. You output a single, \
immediately usable Revid.ai prompt — nothing else.

---

## WHAT REVID.AI MUST DO (YOUR PROMPT MUST COVER ALL 5 ELEMENTS)

1. B-ROLL FOOTAGE
   Layer contextually relevant footage over or beside the talking head. Match the hook theme:
   • Wrongful termination → office/HR/fired scenes
   • Wage theft → paycheck/work floor scenes
   • Protected class → appropriate workplace diversity visuals
   B-roll must feel real and grounded, not stock-photo-generic.

2. CAPTION STYLE
   Burned-in captions, synced to speech. Font: bold sans-serif (Impact or Montserrat Bold).
   Color: white with black drop shadow or stroke. Size: readable on mobile without squinting.
   BOLD HIGHLIGHT the 3 most important phrases per ad (see element 3).

3. CAPTION HIGHLIGHTS
   Automatically bold/color-highlight these specific phrases wherever they appear:
   (a) The hook's key violation phrase
   (b) 'up to $100,000' or '$100,000'
   (c) 'Free Strategy Session'
   Use yellow or bright accent color for highlights against white caption text.

4. PACING & ENERGY
   Match B-roll cut pace to the emotional tone of the script:
   • Hook section = fast cuts (every 1–1.5s)
   • Body section = medium pace (every 2–3s)
   • CTA section = slower, lingering on action shot or logo
   Total video: 20 seconds maximum.

5. LEGAL DISCLAIMER
   Final 3 seconds: black background, white text, centered.
   Text: 'Results may vary. Past results do not guarantee future outcomes. Not legal advice.'
   Font size: small but readable. No voiceover during disclaimer.

---

## B-ROLL THEME LIBRARY BY HOOK TYPE

Hook Type 1 (Broad Unlawful Firing):
  HR meeting room, security badge being returned, office desk being cleared,
  person walking out of building looking defeated

Hook Type 2 (Hyper-Specific Industry / Security):
  Security guard uniform, late-night patrol, paycheck/stub, time clock, warehouse dock

Hook Type 3 (Protected Class / Sick Leave):
  Hospital wristband, doctor's note, medication bottles, HR letter closeup,
  person looking at phone worried

Hook Type 4 (Wage Theft):
  Empty wallet, paycheck with red X, calculator, time clock, person counting cash that's too little

Hook Type 5 (Visual Metaphor / Vacation):
  Cheap motel exterior, stressed family in car, empty parking lot,
  then contrast: beach/resort glimpse

Hook Type 6 (Testimonial / Social Proof):
  Real-looking home setting, person speaking to camera, courthouse exterior,
  legal documents being signed

Hook Type 7 (Pattern Interrupt):
  Closeup of corporate memo, boardroom, employer shaking hands while employee
  watches from background

---

## REVID.AI PROMPT OUTPUT FORMAT

Output ONLY the Revid.ai prompt below. No preamble. No explanation.

REVID.AI EDIT PROMPT:
Source video: [HEYGEN_VIDEO_URL]
Target duration: 20 seconds maximum (hard limit)
B-ROLL: Layer [SPECIFIC B-ROLL THEME from hook type] over the talking head. \
Use real, grounded footage — not generic stock. \
Cut frequency: Hook section = every 1–1.5s. Body = every 2–3s. CTA = 1 sustained shot.
CAPTIONS: Burn-in synced captions. Font: bold sans-serif. White text, black stroke. \
Mobile-optimized size. HIGHLIGHT in yellow: '[HOOK KEY PHRASE]' | 'up to $100,000' | 'Free Strategy Session'.
PACING: Total spoken content = 17 seconds. Reserve final 3 seconds for disclaimer.
DISCLAIMER (seconds 17–20): Black background. White centered text: \
'Results may vary. Past results do not guarantee future outcomes. Not legal advice.' \
No audio. Small readable font.
FORMAT: Portrait 9:16 (primary). Also render Square 1:1 version.
ENERGY: [MATCH TO DIRECTOR'S NOTE FROM SCRIPT — e.g. urgent and authoritative / warm and empathetic]
"""


# ── Main Generator ────────────────────────────────────────────────────────────

async def generate_revid_prompt(
    heygen_video_url: str,
    script: USAEAScript,
) -> str:
    """
    Calls Claude Sonnet 4.6 to generate a Revid.ai edit prompt.

    Args:
        heygen_video_url: The completed Heygen talking head video URL.
        script: The parsed USAEAScript for this ad.

    Returns:
        A Revid.ai edit prompt string, ready to send to the Revid.ai API.
    """
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    user_message = (
        f"Heygen video URL: {heygen_video_url}\n\n"
        f"Original script:\n"
        f"Director's Note: {script.director_note}\n"
        f"Hook Type: {script.hook_type_number} ({script.hook_type_name}) | "
        f"Emotional Trigger: {script.emotional_trigger}\n"
        f"CTA Variant: {script.cta_variant}\n\n"
        f"[HOOK]\n{script.hook_text}\n\n"
        f"[BODY]\n{script.body_text}\n\n"
        f"[CTA]\n{script.cta_text}\n\n"
        f'[DISCLAIMER — on-screen only]\n'
        f'"{script.disclaimer_text}"'
    )

    logger.info(f"Calling Revid.ai Prompt Agent (claude-sonnet-4-6) for Ad #{script.number}...")

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
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
