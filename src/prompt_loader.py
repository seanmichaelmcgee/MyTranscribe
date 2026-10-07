"""
prompt_loader.py — load the Whisper vocabulary prompt for the 1060 edition.

Whisper's "initial prompt" is not an instruction; it is treated as text that
came *before* the audio. Writing it in the style you dictate (a letter
opening dense with your usual drug names, tests and abbreviations) is what
makes those words come out spelled right. Edit prompts/medical_prompt.txt, or
point $MYTRANSCRIBE_PROMPT_FILE at your own file. Only the last ~220 tokens
(roughly 150 words) are used, so keep it short and put the most important
terms near the end.
"""

import logging
import os
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("prompt_loader")

DEFAULT_PROMPT_FILE = Path(__file__).parent / "prompts" / "medical_prompt.txt"
MAX_PROMPT_CHARS = 1200   # ~ whisper's prompt token budget; longer is truncated from the start


def fit_text_budget(text: str, count: Callable[[str], int], budget: int) -> str:
    """Keep a whole-word suffix within a measured token budget.

    Already-fitting text is returned verbatim. Important prompt terms belong at
    the end, matching Whisper's suffix retention. The caller can count a combined
    style/context string to reserve space for recent context. No text is logged.
    """
    if count(text) <= budget:
        return text
    words = text.split()
    low, high = 0, len(words)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = " ".join(words[-middle:])
        if count(candidate) <= budget:
            low = middle
        else:
            high = middle - 1
    # Token counts need not be perfectly monotone at word boundaries. Verify the
    # returned suffix, even if that costs some unused space in an unusual input.
    while low and count(" ".join(words[-low:])) > budget:
        low -= 1
    return " ".join(words[-low:]) if low else ""


def load_prompt(path: Optional[str] = None, env: Optional[dict] = None) -> str:
    """
    Return the prompt text, collapsed to one line.

    Resolution: explicit path > $MYTRANSCRIBE_PROMPT_FILE > bundled default.
    A missing/unreadable file logs an error and returns "" (transcription
    still works, just without vocabulary hints).
    """
    env = os.environ if env is None else env
    chosen = Path(path or env.get("MYTRANSCRIBE_PROMPT_FILE") or DEFAULT_PROMPT_FILE)
    try:
        text = chosen.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Could not read prompt file %s: %s", chosen, exc)
        return ""
    text = " ".join(text.split())
    if len(text) > MAX_PROMPT_CHARS:
        logger.warning("Prompt is %d chars; keeping the last %d", len(text), MAX_PROMPT_CHARS)
        text = text[-MAX_PROMPT_CHARS:]
        text = text[text.find(" ") + 1:]
    logger.info("Loaded %d-char prompt from %s", len(text), chosen)
    return text
