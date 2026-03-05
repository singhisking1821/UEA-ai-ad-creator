WORDS_PER_SECOND = 2.8   # Average conversational speech rate for ad delivery
PAUSE_BUFFER = 1.5       # Seconds added for natural pauses between hook/body/CTA


def estimate_duration(text: str) -> float:
    word_count = len(text.split())
    return (word_count / WORDS_PER_SECOND) + PAUSE_BUFFER


def max_words_for_duration(seconds: float = 22.0) -> int:
    return int((seconds - PAUSE_BUFFER) * WORDS_PER_SECOND)
