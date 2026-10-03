"""
vocab_correct.py — conservative spelling correction of medical terms.

Whisper sometimes writes a near-miss non-word for a drug or term it half
recognised: "licenopril", "renatadine", "metaformin". This module fixes
those, and only those:

  * A word is a candidate ONLY if it is not a known English word
    (wordfreq Zipf frequency < UNKNOWN_ZIPF) and not already a vocabulary term.
    Real words are never touched, so a correctly heard sound-alike
    (hydroxyzine vs hydralazine) can never be "corrected" into the other.
  * The best vocabulary match must be close (edit similarity) and, for the
    lower similarity band, sound the same (Metaphone).
  * The runner-up must be clearly worse; ties are left alone.
  * Words with digits, ALL-CAPS abbreviations and short words are skipped.

Requires the optional packages rapidfuzz, jellyfish and wordfreq. If any is
missing, make_corrector() returns None and transcripts are left as they are.
Corrections are counted but their text is never logged (PHI).
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple

logger = logging.getLogger("vocab_correct")

MIN_WORD_LEN = 5            # shorter words are too ambiguous to fix
UNKNOWN_ZIPF = 1.0          # below this, wordfreq doesn't consider it real English
TARGET_MAX_ZIPF = 3.0       # only fix towards uncommon (medical) words, never "solids"
ACCEPT_SCORE = 88           # similarity (0-100) accepted on spelling alone
PHONETIC_SCORE = 78         # lower band: also needs a Metaphone match
MIN_MARGIN = 6              # best must beat the runner-up by this much
# Near-phonetic band: Metaphone keys one edit apart (e.g. "amlodiphene" AMLTFN vs
# amlodipine AMLTPN: Metaphone turns "ph" into F), accepted only when the match is
# far ahead of every other vocabulary word. From the user's real recordings
# (2026-10-03): amlodiphene -> amlodipine, arithmatous -> erythematous.
NEAR_PHONETIC_MARGIN = 15
MAX_SPAN = 3                # also try joining up to 3 split words ("licen opril")

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")
_TITLE_RE = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Miss|Mx|Prof)\.?$")


def _same_lexeme(a: str, b: str) -> bool:
    """Singular/plural of one word ('vesicle'/'vesicles', 'bulla'/'bullae'): not rival targets."""
    short, long_ = sorted((a, b), key=len)
    return long_ in (short + "s", short + "es", short + "e") or (short.endswith("a") and long_ == short + "e")


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance (short phonetic keys only)."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


@dataclass
class Correction:
    start: int
    end: int
    original: str
    replacement: str
    score: float


class TermCorrector:
    """
    Callable text -> text. Inject the helpers for tests:
      ratio(a, b) -> 0..100, phonetic(word) -> key, zipf(word) -> float
    """

    def __init__(self, terms: Iterable[str], ratio: Callable, phonetic: Callable, zipf: Callable,
                 extract: Optional[Callable] = None) -> None:
        self.ratio, self.phonetic, self.zipf = ratio, phonetic, zipf
        self._extract = extract
        canon = {}
        for term in terms:
            for word in re.split(r"[\s/]+", term):
                word = word.strip(".,;:()")
                for piece in [word] + word.split("-"):
                    if (len(piece) >= MIN_WORD_LEN and piece.isalpha() and not piece.isupper()
                            and self.zipf(piece.lower()) < TARGET_MAX_ZIPF):
                        # Prefer the capitalised (brand) spelling only if it's the only one seen.
                        key = piece.lower()
                        if key not in canon or (canon[key][0].isupper() and not piece[0].isupper()):
                            canon[key] = piece
        self.canonical = canon                 # lower -> display form
        self.choices = list(canon)
        self._phon = {k: self.phonetic(k) for k in self.choices}
        self.total_corrections = 0

    # ── matching ────────────────────────────────────────────────────────────
    def _top2(self, word: str) -> List[Tuple[str, float]]:
        """Best match and the best *different* word (a plural/singular of the best doesn't compete)."""
        if self._extract is not None:
            hits = [(h[0], h[1]) for h in self._extract(word, self.choices, limit=6)]
        else:
            hits = sorted(((c, self.ratio(word, c)) for c in self.choices), key=lambda x: -x[1])[:6]
        if not hits:
            return []
        best = hits[0]
        rivals = [h for h in hits[1:] if not _same_lexeme(best[0], h[0])]
        return [best] + rivals[:1]

    def best_match(self, word: str) -> Optional[Tuple[str, float]]:
        """Vocabulary word for a non-word, or None if no safe unique match."""
        w = word.lower()
        top = self._top2(w)
        if not top:
            return None
        cand, score = top[0]
        second = top[1][1] if len(top) > 1 else 0.0
        if abs(len(cand) - len(w)) > max(2, int(0.3 * len(cand))):
            return None
        if score - second < MIN_MARGIN:
            return None
        if score >= ACCEPT_SCORE:
            return cand, score
        if score >= PHONETIC_SCORE and self.phonetic(w) == self._phon[cand]:
            return cand, score
        if (score >= PHONETIC_SCORE and score - second >= NEAR_PHONETIC_MARGIN
                and _edit_distance(self.phonetic(w), self._phon[cand]) <= 1):
            return cand, score
        return None

    def _is_candidate(self, word: str) -> bool:
        return (len(word) >= MIN_WORD_LEN and not word.isupper()
                and word.lower() not in self.canonical
                and self.zipf(word.lower()) < UNKNOWN_ZIPF)

    # ── public ──────────────────────────────────────────────────────────────
    def find(self, text: str) -> List[Correction]:
        words = [(m.start(), m.end(), m.group()) for m in _WORD_RE.finditer(text)]
        out: List[Correction] = []
        i = 0
        while i < len(words):
            done = False
            # Longest span first, so "licen opril" beats fixing "licen" alone.
            for span in range(min(MAX_SPAN, len(words) - i), 0, -1):
                group = words[i:i + span]
                # Words in a span must be adjacent (only spaces between them).
                if any(text[a[1]:b[0]] != " " for a, b in zip(group, group[1:])):
                    continue
                pieces = [g[2] for g in group]
                if not any(self._is_candidate(p) for p in pieces):
                    continue
                if span > 1 and any(self.zipf(p.lower()) >= 4.0 for p in pieces):
                    continue           # never swallow ordinary words like "and", "on"
                joined = "".join(pieces) if span > 1 else pieces[0]
                if span == 1 and not self._is_candidate(joined):
                    continue
                hit = self.best_match(joined.replace("'", ""))
                if hit:
                    cand, score = hit
                    repl = self.canonical[cand]
                    if pieces[0][0].isupper() and repl.islower():
                        repl = repl[0].upper() + repl[1:]
                    out.append(Correction(group[0][0], group[-1][1], text[group[0][0]:group[-1][1]], repl, score))
                    i += span
                    done = True
                    break
            if not done:
                i += 1
        return out

    def suspicious(self, text: str) -> List[str]:
        """
        Non-words left in `text` (after correction) that the user should check.

        A word is suspicious if it is not English (Zipf < UNKNOWN_ZIPF), not in the
        vocabulary, and not a name: capitalised words that don't start a sentence
        are taken as names and skipped (names don't matter to this user). These
        are the words Whisper made up or merged ("neurothema" = "no erythema") and
        the corrector would not guess at. Whisper's own word confidence does not
        catch them (measured 2026-10-03: 0.78-0.90 on invented words).
        """
        out = []
        for m in _WORD_RE.finditer(text):
            word = m.group()
            for piece in word.split("-"):
                if not self._is_candidate(piece) or not piece.isalpha():
                    continue
                before = text[:m.start()].rstrip()
                after_title = bool(_TITLE_RE.search(before))
                sentence_start = (not before or before[-1] in ".!?:\n\"(") and not after_title
                if piece[0].isupper() and not sentence_start:
                    continue                      # a name
                if piece not in out:
                    out.append(piece)
        return out

    def __call__(self, text: str) -> str:
        fixes = self.find(text)
        if not fixes:
            return text
        parts, last = [], 0
        for f in fixes:
            parts.append(text[last:f.start])
            parts.append(f.replacement)
            last = f.end
        parts.append(text[last:])
        self.total_corrections += len(fixes)
        logger.info("Corrected %d term(s) in chunk", len(fixes))   # count only, no PHI
        return "".join(parts)


def make_corrector(terms: Iterable[str]) -> Optional[TermCorrector]:
    """Build a TermCorrector with rapidfuzz/jellyfish/wordfreq, or None if unavailable."""
    try:
        from rapidfuzz import fuzz, process
        import jellyfish
        from wordfreq import zipf_frequency
    except ImportError as exc:
        logger.warning("Spelling correction disabled (%s); pip install rapidfuzz jellyfish wordfreq", exc)
        return None

    def extract(word, choices, limit=2):
        return [(c, s) for c, s, _ in process.extract(word, choices, scorer=fuzz.ratio, limit=limit)]

    return TermCorrector(terms, ratio=fuzz.ratio, phonetic=jellyfish.metaphone,
                         zipf=lambda w: zipf_frequency(w, "en"), extract=extract)
