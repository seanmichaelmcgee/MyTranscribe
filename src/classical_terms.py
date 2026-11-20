"""
classical_terms.py — put a misheard classical term right where its last word shows what it is.

Whisper often writes an eponym as ordinary words or a near spelling: "Phelan's test" for Phalen's
test, "centaur score" for Centor score, "our rods" for Auer rods, "charcoal foot" for Charcot foot
(term benchmark, docs/testing/README.md, 2026-11-20). The spelling corrector (vocab_correct.py)
cannot fix these: it changes only words that are not English, and these are words or names.

A classical term's last word ("sign", "test", "syndrome", "score", "rods") marks where one sits,
as a dose marks where a drug name sits (drug_names.py). Where that word is heard, the one to three
words before it are compared, by spelling and by sound, with every listed term that ends the same
way. They are replaced only when one term is clearly the closest and close enough. Words that
already make a listed term (or another accepted spelling of one) are left alone, and so are
words the vocabulary knows, so "nephrotic syndrome" and "carpal tunnel syndrome" stay as said.

Terms: vocab/classical_terms.txt. Needs rapidfuzz and jellyfish (and wordfreq for the stricter
rule on everyday words); without them text passes unchanged. Nothing is logged.

Measured 2026-11-20 through the app's own pipeline on the term benchmark's held-out half
(synthetic voices, 4 accents), with the classical words also given to the spelling corrector:
large-v3 84.7% -> 95.7% of terms right, small.en 69.3% -> 88.2%. It changed nothing in the
owner's 47 recordings, the 960 synthetic letters or the 124 saved validation readings.
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

TERMS_FILE = Path(__file__).parent / "vocab" / "classical_terms.txt"

# Where it is on. The owner's rule: what large-v3 works from changes only after full validation,
# so on a graphics card this stays off until the owner approves (docs/testing/README.md).
GRAPHICS_CARD_TOO = False

MAX_SPAN = 3              # words before the last word that may be one misheard name
SCORE = 70                # closeness (0-100), spelling and sound blended, needed to replace
MARGIN = 6                # the best term must beat the next different one by this much
SOUND_WEIGHT = 0.4        # share of the score from the consonant skeleton (Metaphone)
COMMON_ZIPF = 4.0         # a span with an everyday word ("gray", "bone") needs ...
COMMON_SCORE = 85         # ... this much
# Words that never belong to a misheard name at either end of the span.
STOP = {"a", "an", "the", "this", "that", "these", "those", "his", "her", "their", "its", "my",
        "your", "of", "in", "on", "at", "for", "with", "by", "from", "to", "and", "or", "but", "as",
        "no", "not", "was", "is", "were", "are", "be", "been", "has", "had", "have", "positive",
        "negative", "normal", "abnormal", "left", "right", "bilateral", "bilaterally", "mild",
        "moderate", "severe", "acute", "chronic", "new", "old", "recent", "classic", "typical",
        "possible", "probable", "likely", "suspected", "early", "late", "both", "each", "any",
        "some", "also", "very", "small", "large", "high", "low", "full", "repeat", "further",
        # counts and order ("a second fracture"), truth, comparison ("more reflex")
        "first", "second", "third", "fourth", "fifth", "last", "next", "previous", "prior", "another",
        "other", "same", "single", "multiple", "several", "true", "false", "more", "less", "most",
        "least", "better", "worse",
        # where the last word is a verb ("she will score", "please sign", "we test")
        "will", "would", "can", "could", "should", "may", "might", "must", "shall", "did", "does",
        "do", "please", "i", "we", "you", "he", "she", "it", "they", "who", "which", "what"}
# Spellings of a last word that mean the same ("tumor" and "tumour").
SAME_HEAD = {"tumor": "tumour", "maneuver": "manoeuvre", "manoeuver": "manoeuvre",
             "oesophagu": "esophagu", "esophagus": "esophagu"}

_WORD = re.compile(r"[^\W\d_][\w'’\-]*", re.UNICODE)
_JOIN = re.compile(r"^[ \t\-]*$")                    # what may separate words of one term
_SENTENCE_START = re.compile(r"(?:^|[.!?:\n]\s*)$")


def fold(word: str) -> str:
    """A word for matching: lower case, no accents, apostrophes or hyphens, singular, and no
    possessive s ("Phalen's", "Phalen" and "Phalens" all fold alike)."""
    word = unicodedata.normalize("NFKD", word.replace("’", "'"))
    word = "".join(ch for ch in word if not unicodedata.combining(ch)).lower()
    possessive = word.endswith("'s")
    word = re.sub(r"['\-]", "", word[:-2] if possessive else word)
    if possessive:
        pass                                   # "Ogilvie's" is "ogilvie", not a plural
    elif len(word) > 4 and word.endswith("ies"):
        word = word[:-3] + "y"                 # "bodies"
    elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]                       # "nodes", "Homans'", "Phalens"
    return SAME_HEAD.get(word, word)


@dataclass
class Term:
    text: str                 # the right spelling, e.g. "Phalen's test"
    lead: str                 # the words before the last one, as written: "Phalen's"
    lead_key: str             # folded and joined: "phalen"
    head_key: str             # the last word, folded: "test"
    lead_sound: str = ""


def parse_terms(text: str) -> List[List[str]]:
    """[[right spelling, other accepted spellings...]] from the classical_terms.txt format."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append([part.strip() for part in line.split("|") if part.strip()])
    return out


def load_terms(path: Path = TERMS_FILE) -> List[List[str]]:
    try:
        return parse_terms(path.read_text(encoding="utf-8"))
    except OSError:
        return []


def vocabulary(path: Path = TERMS_FILE) -> List[str]:
    """Every listed spelling, for the spelling corrector's vocabulary."""
    return [s for spellings in load_terms(path) for s in spellings]


class ClassicalTermFixer:
    """Callable text -> text. Helpers are injected so the rules can be tested without the libraries."""

    def __init__(self, terms: Iterable[List[str]], ratio: Callable, phonetic: Callable,
                 zipf: Optional[Callable] = None, known: Iterable[str] = ()):
        self.ratio, self.phonetic, self.zipf = ratio, phonetic, zipf or (lambda w: 0.0)
        self.by_head: Dict[str, List[Term]] = {}
        self.valid: Set[Tuple[str, str]] = set()     # (lead key, head key) already right
        for spellings in terms:
            for n, spelling in enumerate(spellings):
                words = _WORD.findall(spelling)
                if len(words) < 2:
                    continue
                last = list(_WORD.finditer(spelling))[-1]
                lead = spelling[:last.start()].rstrip(" -")
                term = Term(spellings[0] if n else spelling, lead, "".join(fold(w) for w in words[:-1]),
                            fold(words[-1]))
                self.valid.add((term.lead_key, term.head_key))
                if n == 0:
                    term.lead_sound = self.phonetic(term.lead_key)
                    self.by_head.setdefault(term.head_key, []).append(term)
        # Words the vocabulary knows ("bowel", "nephrotic"): never taken for a misheard name.
        self.known = {fold(k) for k in known}
        self.total_corrections = 0

    def _score(self, joined: str, term: Term) -> float:
        spell = self.ratio(joined, term.lead_key)
        sound = self.ratio(self.phonetic(joined), term.lead_sound)
        return (1 - SOUND_WEIGHT) * spell + SOUND_WEIGHT * sound

    def _span_ok(self, text: str, span: list, head_start: int) -> bool:
        if fold(span[0][2]) in STOP or fold(span[-1][2]) in STOP:
            return False
        ends = [w[1] for w in span]
        starts = [w[0] for w in span[1:]] + [head_start]
        return all(_JOIN.match(text[a:b]) for a, b in zip(ends, starts))

    def _fix_at(self, text: str, words: list, j: int) -> Optional[Tuple[int, int, str]]:
        """(start, end, replacement) for the words before the last word words[j], or None."""
        head = fold(words[j][2])
        terms = self.by_head.get(head)
        if not terms:
            return None
        spans = []
        for n in range(1, min(MAX_SPAN, j) + 1):
            span = words[j - n:j]
            if not self._span_ok(text, span, words[j][0]):
                continue
            keys = [fold(w[2]) for w in span]
            joined = "".join(keys)
            if (joined, head) in self.valid:
                return None                           # already a listed term
            spans.append((span, keys, joined))
        scored = []
        for span, keys, joined in spans:
            if all(k in self.known for k in keys):
                continue                              # words the vocabulary knows ("nephrotic")
            common = any(self.zipf(k) >= COMMON_ZIPF for k in keys)
            for term in terms:
                if abs(len(joined) - len(term.lead_key)) > max(3, 0.4 * len(term.lead_key)):
                    continue
                scored.append((self._score(joined, term), common, span, term))
        if not scored:
            return None
        scored.sort(key=lambda x: -x[0])
        score, common, span, term = scored[0]
        second = next((s for s, _, _, t in scored[1:] if t.text != term.text), 0.0)
        if score < (COMMON_SCORE if common else SCORE) or score - second < MARGIN:
            return None
        lead = term.lead
        if lead[:1].islower() and _SENTENCE_START.search(text[:span[0][0]]):
            lead = lead[0].upper() + lead[1:]
        return span[0][0], span[-1][1], lead

    def __call__(self, text: str) -> str:
        words = [(m.start(), m.end(), m.group().rstrip("-")) for m in _WORD.finditer(text)]
        fixes, taken = [], -1
        for j in range(1, len(words)):
            fix = self._fix_at(text, words, j)
            if fix and fix[0] > taken and text[fix[0]:fix[1]] != fix[2]:
                fixes.append(fix)
                taken = fix[1]
        if not fixes:
            return text
        parts, last = [], 0
        for start, end, repl in fixes:
            parts += [text[last:start], repl]
            last = end
        parts.append(text[last:])
        self.total_corrections += len(fixes)
        return "".join(parts)


def make_fixer(known: Iterable[str] = (), path: Path = TERMS_FILE) -> Optional[ClassicalTermFixer]:
    try:
        import jellyfish
        from rapidfuzz import fuzz
    except ImportError:
        return None
    try:
        from wordfreq import zipf_frequency
        zipf = lambda w: zipf_frequency(w, "en")          # noqa: E731
    except ImportError:
        zipf = None
    return ClassicalTermFixer(load_terms(path), ratio=fuzz.ratio, phonetic=jellyfish.metaphone, zipf=zipf,
                              known=known)


def on_for(engine) -> bool:
    """Is the fixer on for this recogniser? Whisper on the processor; on a graphics card only
    with GRAPHICS_CARD_TOO. Other recognisers (no Whisper config) never."""
    device = getattr(getattr(engine, "config", None), "device", None)
    return device == "cpu" or (device == "cuda" and GRAPHICS_CARD_TOO)


_DEFAULT = None


def default_fixer() -> Optional[ClassicalTermFixer]:
    """One fixer for the app, knowing the vocabulary's words so it leaves them alone."""
    global _DEFAULT
    if _DEFAULT is None:
        try:
            import vocab
            known = {w for t in vocab.load_lexicon().all_terms() for w in _WORD.findall(t.text)}
        except Exception:
            known = set()
        _DEFAULT = make_fixer(known) or False
    return _DEFAULT or None


def apply(text: str) -> str:
    fixer = default_fixer()
    return fixer(text) if fixer else text
