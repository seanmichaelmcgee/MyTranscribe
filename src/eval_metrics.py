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
from typing import Iterable, List, Tuple

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


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def term_hits(terms: Iterable[str], hypothesis: str) -> Tuple[List[str], List[str]]:
    """(found, missed) target terms, ignoring case, hyphens and spaces."""
    hyp = _squash(hypothesis)
    found, missed = [], []
    for term in terms:
        (found if _squash(term) and _squash(term) in hyp else missed).append(term)
    return found, missed
