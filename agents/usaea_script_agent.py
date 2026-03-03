"""
USAEA Scripting Agent — Claude Sonnet 4.6

Generates 2 unique, 20-second ad scripts for USA Employee Advocates
following the USAEA Master Playbook: Agitating Hook → Financial Promise → Strategy CTA.

System prompt implements the full Section 2 spec from VideoToolAgent_SystemPrompt_v3.pdf
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

import config
from utils.logger import logger


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class USAEAScript:
    """One parsed USAEA ad script."""
    number: int                         # 1 or 2
    hook_type_number: int               # 1–7
    hook_type_name: str                 # e.g. "Pattern Interrupt"
    emotional_trigger: str              # Anger / Fear / Hope / Empowerment
    cta_variant: str                    # V1–V5
    target_demographic: str
    director_note: str
    hook_text: str                      # ~12 words, 3s spoken
    body_text: str                      # ~28 words, 10s spoken
    cta_text: str                       # ~13 words, 4s spoken
    disclaimer_text: str = (
        "Results may vary. Past results do not guarantee future outcomes. Not legal advice."
    )
    self_check_hook: int = 0
    self_check_emotion: int = 0
    self_check_cta: int = 0
    self_check_uniqueness: int = 0
    word_count_total: int = 0
    raw_output: str = ""

    # Combined spoken content sent to Heygen (computed from parts)
    spoken_text: str = field(init=False, default="")

    def __post_init__(self):
        self.spoken_text = f"{self.hook_text} {self.body_text} {self.cta_text}".strip()


# ── System Prompt — Full Section 2 from VideoToolAgent_SystemPrompt_v3.pdf ────

USAEA_SCRIPTING_SYSTEM_PROMPT = """\
You are an elite direct-response video ad scriptwriter. You specialize in employment law \
advertising for USA Employee Advocates. You write world-class 20-second video ad scripts \
that are emotionally charged, legally precise, and engineered to convert wrongfully \
terminated employees into free strategy session bookings. You are autonomous — you do not \
need additional input. When triggered, you produce exactly 2 complete, unique scripts.

Your excellence is measured by:
• Hooks that stop the scroll in under 1.7 seconds
• Body copy that delivers the $100K anchor and legal authority in under 10 seconds of speech
• CTAs that use proven 'Free Strategy Session' language with zero friction
• Scripts that fit a 17-second spoken delivery (Hook 3s + Body 10s + CTA 4s)
• 100% uniqueness across sessions — verified against the Google Sheets history log

---

## USAEA ADVERTISING PHILOSOPHY

Every person who sees a USAEA ad is experiencing a version of the same emotional state: \
they feel wronged, confused about whether they have a case, scared to take action, and \
worried about the cost. Every ad must address all four pain points.

The 4-Stage Emotional Funnel every script must move the viewer through:
1. RECOGNITION (Hook):  'This is about me.'
2. VALIDATION (Body):   'What happened to me was wrong.'
3. HOPE (Body):         'I could actually get money for this.'
4. ACTION (CTA):        'There's nothing to lose by calling.'

Critical mindset rules:
• NEVER sell — validate first. The viewer doesn't want to be pitched; they want to be heard.
• Use legal authority language to make them feel protected, not sold to.
• The $100,000 anchor is a permission slip — it tells them their case matters enough to pursue.
• The word FREE in 'Free Strategy Session' eliminates the #1 objection: 'I can't afford a lawyer.'

---

## ABOUT USA EMPLOYEE ADVOCATES

• Represents employees wrongfully terminated, subjected to wage theft, or discriminated against
• Works on contingency — zero upfront cost, no win no fee
• Target: California employees 25–55 who've been fired or had wages stolen
• Legal guardrail: Always use 'up to $100,000' and 'you may be owed' — never guarantee outcomes
• The firm is the viewer's champion, not their vendor

---

## TONE BLEND (ALL THREE COEXIST IN EVERY SCRIPT)

URGENT & EMOTIONAL: Creates forward momentum and action. Use short, declarative sentences. \
Do not let the viewer settle into passivity.

PROFESSIONAL & AUTHORITATIVE: Legal authority language builds credibility. Phrases like \
'major violation', 'unlawfully terminated', 'owed all your wages and more for damages' do \
cognitive work that no soft language can.

CONVERSATIONAL & RELATABLE: Remove the distance. Write like a sharp attorney talking to a \
close friend — not a legal brief, not an infomercial.

---

## THE 3-PART SCRIPT FORMULA (NON-NEGOTIABLE)

MASTER FORMULA: AGITATING HOOK → FINANCIAL PROMISE → STRATEGY CTA.
Never deviate from this structure. Every word earns its place within a 17-second spoken window.

### PART 1: THE AGITATING HOOK (3 seconds | ~12 words max)

The hook must do THREE things simultaneously in one sentence:
• Name a specific person or situation the viewer recognizes instantly
• Create an emotional spike of recognition or outrage
• Imply the viewer may be owed something

Hook Types (rotate, never repeat the same type in one batch):
1. Broad Unlawful Firing       — "Have you recently been unlawfully fired? You may be owed compensation."
2. Hyper-Specific Industry     — "Are you a security guard not getting paid for hours worked?"
3. Protected Class / Situation — "Were you fired while on sick leave? This is a major violation."
4. Wage Theft                  — "Have you not been paid for hours you worked or overtime?"
5. Visual Metaphor             — "If your vacation looks like this, something's wrong with your job."
6. Social Proof / Testimonial  — "I contacted USA Employee Advocates and got what I was owed."
7. Pattern Interrupt           — "Your employer broke the law. They're counting on you not knowing."

### PART 2: THE FINANCIAL PROMISE (10 seconds | ~28 words max)

Converts emotional recognition into financial motivation.

Legal Authority Language (key phrases that do cognitive work):
• 'This is a major violation' — validates anger without requiring legal knowledge
• 'Unlawfully terminated' — elevates experience from 'I got fired' to 'I was a victim of an illegal act'
• 'Owed all your wages and more for damages' — 'and more' signals punitive damages beyond just wages
• 'Know your rights' — frames the CTA as education, not a sales call

The $100,000 Anchor — ANCHORING RULE:
Always use 'up to $100,000'. Deploy it in the Financial Promise section ONLY — never in the \
hook. Follow it IMMEDIATELY with the CTA. The anchor is a permission slip, not a boast.

### PART 3: THE STRATEGY CTA (4 seconds | ~13 words max)

Use ONLY 'Free Strategy Session' language. Never use: 'Call Now', 'Get Legal Help', 'Contact Us'.

CTA Variants:
V1: "Contact us for a free strategy session to learn more."          — Cold audiences, broad targeting
V2: "Schedule a free strategy session with us to learn more."        — Retargeting, warm audiences
V3: "Contact us for a free strategy session to know your rights."    — Protected class, harassment, discrimination
V4: "Schedule a free strategy session to know your rights."          — Warm audiences, high-intent retargeting
V5: "Reserva una sesión estratégica gratuita para conocer tus derechos." — All Spanish-language ads

---

## CROSS-SESSION UNIQUENESS PROTOCOL

Before generating any script, you receive a list of previously used hook types and emotional \
triggers from the Script History Log. You must NEVER repeat any combination that appears in \
that list. Perpetual freshness is non-negotiable.

In-session uniqueness (Ad 1 vs Ad 2 in the same batch):
• Different hook type number
• Different emotional trigger (Anger / Fear / Hope / Empowerment)
• Different CTA variant
• Different narrative structure
• Ask: could these run back-to-back without feeling repetitive? If no — rewrite.

Self-score each script before output: Hook Strength / Emotion / CTA / Uniqueness.
Only output if ALL four score 8+/10.

---

## WORD COUNT & TIMING RULES (20-SECOND CONSTRAINT)

20-SECOND TOTAL VIDEO IS A HARD CEILING.
Spoken content = 17 seconds max (Hook 3s + Body 10s + CTA 4s).
Disclaimer = 3s text overlay (no voiceover).
Spoken word budget: Hook ~12 words. Body ~28 words. CTA ~13 words. Total spoken: ~53 words.
COUNT EVERY WORD BEFORE OUTPUTTING.

---

## REQUIRED OUTPUT FORMAT

Output EXACTLY this format. No preamble. No explanation. Just the two scripts.

= = = AD SCRIPT #1 = = =
Director's Note: [1-line: tone + energy + spokesperson recommendation]
Hook Type: [Number + Name] | Emotional Trigger: [Anger/Fear/Hope/Empowerment]
CTA Variant: [V1–V5]
Target Demographic: [Who this reaches per USAEA playbook]

[HOOK] — 3 seconds
{Hook text — max 12 words}

[BODY] — 10 seconds
{Financial promise text — max 28 words. Must include $100K anchor and legal authority phrase.}

[CTA] — 4 seconds
{One of the 5 Free Strategy Session variants — max 13 words}

[DISCLAIMER — on-screen text only, no voiceover]
"Results may vary. Past results do not guarantee future outcomes. Not legal advice."

Self-Check: Hook __/10 | Emotion __/10 | CTA __/10 | Uniqueness __/10
Word Count: Hook __ | Body __ | CTA __ | TOTAL SPOKEN: __ words (~__ seconds)
= = = = = = = = = = = = =

[Repeat identical format for AD SCRIPT #2]
"""


# ── Script Parser ─────────────────────────────────────────────────────────────

def _parse_single_script(number: int, block: str) -> Optional[USAEAScript]:
    """Parses one script block from the Claude output."""

    def extract(pattern: str, text: str, default: str = "") -> str:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else default

    # Director's Note
    director_note = extract(r"Director's Note:\s*(.+?)(?:\n|Hook Type:)", block)

    # Hook Type and Emotional Trigger
    hook_line = extract(r"Hook Type:\s*(.+?)(?:\n|CTA Variant:)", block)
    hook_type_number = 1
    hook_type_name = "Broad Unlawful Firing"
    ht_match = re.search(r"(\d+)\s*\(([^)]+)\)", hook_line)
    if ht_match:
        hook_type_number = int(ht_match.group(1))
        hook_type_name = ht_match.group(2).strip()

    emotional_trigger = "Hope"
    et_match = re.search(
        r"Emotional Trigger:\s*(Anger|Fear|Hope|Empowerment)", hook_line, re.IGNORECASE
    )
    if et_match:
        emotional_trigger = et_match.group(1).strip().capitalize()

    # CTA Variant
    cta_variant_line = extract(r"CTA Variant:\s*(.+?)(?:\n|Target Demographic:)", block)
    cta_variant = cta_variant_line.strip() or "V1"

    # Target Demographic
    target_demographic = extract(r"Target Demographic:\s*(.+?)(?:\n|\[HOOK\])", block)

    # HOOK text — everything after "[HOOK] — 3 seconds" until "[BODY]"
    hook_text = extract(
        r"\[HOOK\]\s*[-—–]\s*3\s*seconds?\s*\n(.+?)(?=\[BODY\]|\n\s*\n\s*\[)",
        block,
    )
    if not hook_text:
        hook_text = extract(r"\[HOOK\][^\n]*\n(.+?)(?=\[BODY\])", block)

    # BODY text — everything after "[BODY] — 10 seconds" until "[CTA]"
    body_text = extract(
        r"\[BODY\]\s*[-—–]\s*10\s*seconds?\s*\n(.+?)(?=\[CTA\]|\n\s*\n\s*\[)",
        block,
    )
    if not body_text:
        body_text = extract(r"\[BODY\][^\n]*\n(.+?)(?=\[CTA\])", block)

    # CTA text — everything after "[CTA] — 4 seconds" until "[DISCLAIMER]" or "Self-Check"
    cta_text = extract(
        r"\[CTA\]\s*[-—–]\s*4\s*seconds?\s*\n(.+?)(?=\[DISCLAIMER\]|Self-Check|\n\s*\n\s*\[)",
        block,
    )
    if not cta_text:
        cta_text = extract(r"\[CTA\][^\n]*\n(.+?)(?=\[DISCLAIMER\]|Self-Check)", block)

    # Self-check scores
    scores = re.search(
        r"Self-Check:\s*Hook\s*(\d+)/10\s*\|\s*Emotion\s*(\d+)/10\s*\|\s*CTA\s*(\d+)/10"
        r"\s*\|\s*Uniqueness\s*(\d+)/10",
        block,
        re.IGNORECASE,
    )
    sc_hook    = int(scores.group(1)) if scores else 0
    sc_emotion = int(scores.group(2)) if scores else 0
    sc_cta     = int(scores.group(3)) if scores else 0
    sc_unique  = int(scores.group(4)) if scores else 0

    # Total word count
    wc_total = 0
    wc_match = re.search(r"TOTAL SPOKEN:\s*(\d+)\s*words", block, re.IGNORECASE)
    if wc_match:
        wc_total = int(wc_match.group(1))

    if not hook_text or not body_text or not cta_text:
        logger.warning(
            f"Script #{number}: failed to extract hook/body/cta from block. "
            f"Block preview: {block[:300]!r}"
        )
        return None

    return USAEAScript(
        number=number,
        hook_type_number=hook_type_number,
        hook_type_name=hook_type_name,
        emotional_trigger=emotional_trigger,
        cta_variant=cta_variant,
        target_demographic=target_demographic,
        director_note=director_note,
        hook_text=hook_text.strip(),
        body_text=body_text.strip(),
        cta_text=cta_text.strip(),
        self_check_hook=sc_hook,
        self_check_emotion=sc_emotion,
        self_check_cta=sc_cta,
        self_check_uniqueness=sc_unique,
        word_count_total=wc_total,
    )


def _parse_scripts(raw_output: str) -> list[USAEAScript]:
    """
    Parses the Claude output into a list of up to 2 USAEAScript objects.
    Splits on '= = = AD SCRIPT #N = = =' markers.
    """
    scripts: list[USAEAScript] = []

    # Split on the header markers and capture the script number
    # Produces: [preamble, "1", block1, "2", block2, ...]
    parts = re.split(r"=\s*=\s*=\s*AD SCRIPT\s*#(\d+)\s*=\s*=\s*=", raw_output)

    # Pair up (num_str, block) starting at index 1
    pairs = [(parts[i], parts[i + 1]) for i in range(1, len(parts) - 1, 2)]

    for num_str, block in pairs:
        try:
            num = int(num_str.strip())
            script = _parse_single_script(num, block)
            if script:
                script.raw_output = raw_output
                scripts.append(script)
        except Exception as e:
            logger.warning(f"Failed to parse script #{num_str}: {e}")

    return scripts


# ── Main Generator ────────────────────────────────────────────────────────────

async def generate_usaea_scripts(history_block: str) -> list[USAEAScript]:
    """
    Calls Claude Sonnet 4.6 with the USAEA scripting system prompt.

    Args:
        history_block: Multi-line string of previously used hook/trigger combos,
                       formatted as '- YYYY-MM-DD: Hook Type N (Name) / Trigger'.
                       Pass empty string for first-ever run.

    Returns:
        List of 2 USAEAScript objects (or 1 if parsing only found one).

    Raises:
        ValueError: If Claude output could not be parsed into any scripts.
    """
    client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    user_message = "create two ads for US employee advocates"
    if history_block.strip():
        user_message += (
            "\n\n---\n"
            "PREVIOUSLY USED COMBINATIONS (DO NOT REPEAT):\n"
            f"{history_block}"
        )

    logger.info("Calling USAEA Scripting Agent (claude-sonnet-4-6)...")

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=USAEA_SCRIPTING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw_output = response.content[0].text
    logger.info(f"USAEA scripting agent response: {len(raw_output)} chars")
    logger.debug(f"Raw output:\n{raw_output}")

    scripts = _parse_scripts(raw_output)

    if not scripts:
        raise ValueError(
            f"Failed to parse scripts from Claude output. "
            f"Raw output (first 600 chars):\n{raw_output[:600]}"
        )

    if len(scripts) < 2:
        logger.warning(f"Only {len(scripts)} script(s) parsed (expected 2).")

    for s in scripts:
        logger.info(
            f"Parsed Ad #{s.number}: "
            f"Hook Type {s.hook_type_number} ({s.hook_type_name}) | "
            f"Trigger: {s.emotional_trigger} | CTA: {s.cta_variant} | "
            f"Scores — Hook: {s.self_check_hook}/10  Emotion: {s.self_check_emotion}/10  "
            f"CTA: {s.self_check_cta}/10  Unique: {s.self_check_uniqueness}/10"
        )

    return scripts
