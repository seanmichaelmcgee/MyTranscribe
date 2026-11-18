"""
tuning/score.py — the clinical fields a setting must never break.

Word error rate treats every word alike. A setting is only acceptable if it adds no
error in a number, a negation or a drug name, so these are counted on their own
(docs/settings/README.md, rule 3). Shared by the settings suite and, later, setup.
"""

from typing import Callable, Dict

from eval_metrics import align, normalize_words

NEGATIONS = {"no", "not", "nor", "none", "never", "without", "negative", "denies", "cannot", "nil"}


def is_number(word: str) -> bool:
    return any(ch.isdigit() for ch in word)


def clinical_errors(reference: str, hypothesis: str,
                    is_medical: Callable[[str], bool] = lambda w: False) -> Dict[str, int]:
    """
    Errors in the fields that change meaning: reference numbers, negations and medical
    words that were substituted or dropped, plus negations the output added.
    Returns counts and the totals they are out of.
    """
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    out = {"numbers": 0, "numbers_of": 0, "negations": 0, "negations_of": 0, "medical": 0, "medical_of": 0}
    for w in ref:
        out["numbers_of"] += is_number(w)
        out["negations_of"] += w in NEGATIONS
        out["medical_of"] += bool(is_medical(w)) and not is_number(w)
    for op, ri, hj in align(ref, hyp):
        if op == "ok":
            continue
        if ri is not None:
            w = ref[ri]
            if is_number(w):
                out["numbers"] += 1
            elif w in NEGATIONS:
                out["negations"] += 1
            elif is_medical(w):
                out["medical"] += 1
        elif hj is not None and hyp[hj] in NEGATIONS:
            out["negations"] += 1                    # a negation that was never said
    return out
