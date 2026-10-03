"""
text_fixes.py — small deterministic clean-ups applied to every transcribed chunk.

1. Spelled-out abbreviations. Whisper writes letter-by-letter dictation as
   "H-E-E-N-T" or "C, V, A". Hyphen-joined single letters are always joined
   ("H-E-E-N-T" -> "HEENT"). Space/comma-separated letters are joined only when
   the result is a known abbreviation from the vocabulary, so a real list like
   "A, B, C" is left alone.

2. Personal corrections ("heard => correct"), like Dragon's vocabulary editor:
   one rule per line in plain-text files; whole words/phrases, case-insensitive.
     anti-Rho => anti-Ro
   Bundled file: vocab/corrections.txt. Your own: %APPDATA%\\MyTranscribe\\corrections.txt
   (or $MYTRANSCRIBE_CORRECTIONS_FILE). Lines starting with # are comments.

Pure functions; nothing is logged.
"""

import os
import re
import sys
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set, Tuple

BUNDLED_CORRECTIONS = Path(__file__).parent / "vocab" / "corrections.txt"

_HYPHEN_LETTERS = re.compile(r"\b(?:[A-Za-z]-){1,9}[A-Za-z]\b")
_SPACED_LETTERS = re.compile(r"\b(?:[A-Za-z][.,]?\s+){1,9}[A-Za-z]\b\.?")


def join_spelled_letters(text: str, known: Set[str] = frozenset()) -> str:
    """'H-E-E-N-T' -> 'HEENT' always; 'C, V, A' -> 'CVA' only if 'CVA' is a known abbreviation."""
    def hyphen(m):
        return m.group(0).replace("-", "").upper()

    def spaced(m):
        letters = re.findall(r"[A-Za-z]", m.group(0))
        joined = "".join(letters).upper()
        if len(letters) >= 2 and joined.lower() in known:
            # Keep a final "." only where a sentence really ends (text end, or a capital next).
            rest = m.string[m.end():]
            ends_sentence = m.group(0).endswith(".") and (not rest.strip() or re.match(r"\s+[A-Z\n]", rest))
            return joined + ("." if ends_sentence else "")
        return m.group(0)
    text = _HYPHEN_LETTERS.sub(hyphen, text)
    return _SPACED_LETTERS.sub(spaced, text)


def default_user_corrections_path() -> Path:
    env = os.environ.get("MYTRANSCRIBE_CORRECTIONS_FILE", "").strip()
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "MyTranscribe" / "corrections.txt"
    return Path.home() / ".config" / "mytranscribe" / "corrections.txt"


def load_corrections(paths: Iterable[Path]) -> List[Tuple[re.Pattern, str]]:
    """Parse 'heard => correct' rules; later files win for the same 'heard'."""
    rules = {}
    for path in paths:
        try:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or "=>" not in line:
                continue
            heard, correct = (s.strip() for s in line.split("=>", 1))
            if heard and correct:
                rules[heard.lower()] = correct
    out = []
    for heard, correct in sorted(rules.items(), key=lambda kv: -len(kv[0])):   # longest first
        words = [re.escape(w) for w in re.split(r"[\s-]+", heard)]
        pat = re.compile(r"(?<![\w-])" + r"[\s-]+".join(words) + r"(?![\w-])", re.IGNORECASE)
        out.append((pat, correct))
    return out


def apply_corrections(text: str, rules: List[Tuple[re.Pattern, str]]) -> str:
    for pat, correct in rules:
        text = pat.sub(correct, text)
    return text


def make_text_fixes(known_abbreviations: Set[str],
                    correction_files: Optional[Iterable[Path]] = None) -> Callable[[str], str]:
    """Chunk post-processor: spelled-letter joining, then personal corrections."""
    files = list(correction_files) if correction_files is not None else [BUNDLED_CORRECTIONS,
                                                                          default_user_corrections_path()]
    rules = load_corrections(files)
    known = {a.lower() for a in known_abbreviations}

    def fix(text: str) -> str:
        return apply_corrections(join_spelled_letters(text, known), rules)
    return fix
