"""
eval_metrics.py — scoring for dictation tests: word error rate and medical-term recall.

WER alone undersells what matters in clinical dictation: getting "the" wrong is
harmless, getting "apixaban" wrong is not. So we also report term recall —
the share of the target medical terms (listed per test file) that appear in
the transcript, compared case-, hyphen- and spacing-insensitively.

Normalisation is deliberately simple and symmetric (applied to both sides):
lower-case, units/number words mapped to one spelling, punctuation dropped.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set, Tuple

_UNIT_WORDS = {
    "milligrams": "mg", "milligram": "mg", "micrograms": "mcg", "microgram": "mcg",
    "millilitres": "ml", "milliliters": "ml", "millilitre": "ml", "milliliter": "ml",
    "kilograms": "kg", "kilogram": "kg", "percent": "%", "per": "/",
}
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "fifteen": "15", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "hundred": "100", "thousand": "1000",
}


def normalize_words(text: str) -> List[str]:
    """Lower-case word list with units/numbers unified and punctuation removed."""
    t = text.lower().replace("%", " % ")
    t = re.sub(r"(\d)\s*(mg|mcg|ml|kg)\b", r"\1 \2", t)
    t = re.sub(r"[^a-z0-9%/ ]+", " ", t)
    out = []
    for w in t.split():
        w = _UNIT_WORDS.get(w, w)
        w = _NUMBER_WORDS.get(w, w)
        out.append(w)
    return out


def word_error_rate(reference: str, hypothesis: str) -> Tuple[float, int]:
    """(WER, reference word count) using word-level Levenshtein distance."""
    r, h = normalize_words(reference), normalize_words(hypothesis)
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = cur
    return (prev[len(h)] / max(1, len(r))), len(r)


def align(ref: List[str], hyp: List[str]) -> List[Tuple[str, Optional[int], Optional[int]]]:
    """
    Word alignment with minimum edits. Returns ops in order:
    ("ok"|"sub"|"del"|"ins", ref_index or None, hyp_index or None).
    """
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = i
    for j in range(1, m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]))
    ops, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1] != hyp[j - 1]):
            ops.append(("ok" if ref[i - 1] == hyp[j - 1] else "sub", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", i - 1, None))
            i -= 1
        else:
            ops.append(("ins", None, j - 1))
            j -= 1
    return ops[::-1]


TITLES = {"dr", "mr", "mrs", "ms", "miss", "mx"}


@dataclass
class Breakdown:
    """Errors split the way a clinician cares about them (one utterance or summed)."""
    words: int = 0                 # reference words, names excluded
    errors: int = 0                # edits, name errors free
    medical: int = 0               # reference medical words
    medical_errors: int = 0
    common: int = 0                # reference everyday words (Zipf >= common_zipf)
    common_errors: int = 0
    invented: List[str] = field(default_factory=list)       # rare words output but never said
    medical_missed: List[str] = field(default_factory=list)

    def add(self, other: "Breakdown") -> "Breakdown":
        for k in ("words", "errors", "medical", "medical_errors", "common", "common_errors"):
            setattr(self, k, getattr(self, k) + getattr(other, k))
        self.invented += other.invented
        self.medical_missed += other.medical_missed
        return self

    def rates(self) -> dict:
        pct = lambda a, b: round(100 * a / b, 1) if b else 0.0
        return {"wer": pct(self.errors, self.words), "medical_wer": pct(self.medical_errors, self.medical),
                "common_wer": pct(self.common_errors, self.common),
                "invented_per_100": pct(len(self.invented), self.words)}


def breakdown(reference: str, hypothesis: str, names: Iterable[str] = (),
              is_medical: Callable[[str], bool] = lambda w: False,
              zipf: Callable[[str], float] = lambda w: 5.0,
              common_zipf: float = 4.0, invented_zipf: float = 3.0) -> Breakdown:
    """
    Name-insensitive scoring with medical / common / invented-word detail.

    - Names (and titles like Dr/Mrs) don't count: substituting, dropping or
      re-spelling them (including extra words next to them) is free.
    - medical_errors: reference medical words substituted or dropped.
    - common_errors: reference everyday words substituted or dropped.
    - invented: output words that appear nowhere in the reference and are
      rare in English (likely confabulated, e.g. "psoas" for "shows").
    """
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    name_set = {w for n in names for w in normalize_words(n)} | TITLES
    ops = align(ref, hyp)
    is_name = [w in name_set for w in ref]
    # Insertions directly next to a name edit are part of re-spelling the name.
    near_name = set()
    for k, (op, ri, hj) in enumerate(ops):
        if op == "ins":
            for nb in (k - 1, k + 1):
                if 0 <= nb < len(ops) and ops[nb][1] is not None and is_name[ops[nb][1]]:
                    near_name.add(k)
    ref_set = set(ref)
    b = Breakdown()
    for i, w in enumerate(ref):
        if is_name[i]:
            continue
        b.words += 1
        if is_medical(w):
            b.medical += 1
        elif zipf(w) >= common_zipf:
            b.common += 1
    for k, (op, ri, hj) in enumerate(ops):
        if op == "ok":
            continue
        if ri is not None and is_name[ri]:
            continue
        if op == "ins" and k in near_name:
            continue
        b.errors += 1
        if ri is not None:
            w = ref[ri]
            if is_medical(w):
                b.medical_errors += 1
                b.medical_missed.append(w)
            elif zipf(w) >= common_zipf:
                b.common_errors += 1
        if hj is not None:
            h = hyp[hj]
            if h not in ref_set and h.isalpha() and zipf(h) < invented_zipf:
                b.invented.append(h)
    return b


def load_medical_words(paths: Iterable[Path], zipf: Callable[[str], float],
                       max_zipf: float = 4.0) -> Set[str]:
    """Words from vocabulary files that are rare in everyday English (= 'medical words')."""
    words: Set[str] = set()
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or (line.startswith("#") and not line.startswith("##")):
                continue                                   # comment
            if line.startswith("##"):                      # "## topic | trigger words"
                body = line.split("|", 1)[1] if "|" in line else ""
            elif ":" in line:                              # "category: term, term"
                body = line.split(":", 1)[1]
            else:                                          # tab-separated list ("acronym\tTSH")
                body = line.split("\t")[-1]
            for w in normalize_words(body.replace("\t", " ")):
                if w.isalpha() and len(w) > 2 and zipf(w) < max_zipf:
                    words.add(w)
    return words


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def term_hits(terms: Iterable[str], hypothesis: str) -> Tuple[List[str], List[str]]:
    """(found, missed) target terms, ignoring case, hyphens and spaces."""
    hyp = _squash(hypothesis)
    found, missed = [], []
    for term in terms:
        (found if _squash(term) and _squash(term) in hyp else missed).append(term)
    return found, missed
