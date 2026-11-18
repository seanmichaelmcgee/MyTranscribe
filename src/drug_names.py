"""
drug_names.py — put a misheard drug name right when the sentence says a drug belongs there.

The general spelling corrector (vocab_correct.py) only changes a non-word that
is nearly identical to one vocabulary term, because it runs on every word. A
drug name is easier: it sits in a recognisable place ("takes ___ 5 mg daily",
"medications include ___"), so a much looser match is safe there. Three bands:

  anywhere      an unknown word within a letter or two of a drug name
                ("osmertinib" -> "osimertinib")
  in a drug     an unknown word that is the closest thing to one drug name
  position      ("capragone 0.5 mg" -> "cabergoline")
  before a dose ordinary words that together sound exactly like a drug name
                ("Ram and Pearl 5 mg" -> "ramipril"), and a leading digit read
                as a syllable ("4-Motorol" -> "formoterol")

Names come from vocab/drug_names.txt (RxNorm generic names, public domain), plus
the brand names in the vocabulary files and the user's medications list.
Part of Extra corrections; English only. Needs rapidfuzz, jellyfish and
wordfreq (as the spelling corrector does); without them text passes unchanged.
Nothing is logged.
"""

import re
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Set, Tuple

DRUG_FILE = Path(__file__).parent / "vocab" / "drug_names.txt"

ANYWHERE_SCORE = 86       # spelling similarity (0-100) accepted wherever the word is
SLOT_SCORE = 74           # in a drug position
SLOT_MARGIN = 1           # best must beat the next different drug by this much
SOUND_SCORE = 55          # with the same consonant skeleton, in a drug position
SOUND_WEIGHT = 0.4        # share of the score that comes from the consonant skeleton (Metaphone)
COMMON_BONUS = 3         # everyday drugs win near-ties against rare ones
PREFERRED_BONUS = 12      # the user's usual medications win close calls ("mesoprolol": bisoprolol)
PREFERRED_FLOOR = 65
UNKNOWN_ZIPF = 1.5        # below this the word is not ordinary English
MIN_LEN = 5
MAX_SPAN = 3

_UNIT = r"(?:mg|mcg|µg|g|kg|mL|IU|mEq|units?|puffs?|tablets?|tabs?|capsules?|drops?|sprays?|patch(?:es)?|%)"
_DOSE = r"\d[\d.,/]*\s?" + _UNIT + r"\b"
_FREQ = (r"(?:(?:once|twice|two times|three times|four times)\s+(?:a\s+|per\s+)?(?:daily|day|weekly|week|nightly)"
         r"|daily|weekly|nightly|monthly|as needed|at bedtime|at night|every\s+(?:morning|evening|night|day|other day|\d+\s+hours)"
         r"|in the (?:morning|evening)|PRN|BID|TID|QID|QHS)\b")
_AFTER_SLOT = re.compile(r"^\s*,?\s*(?:" + _DOSE + "|" + _FREQ + ")", re.I)
_AFTER_DOSE = re.compile(r"^\s*,?\s*" + _DOSE, re.I)
_CUE = re.compile(r"\b(?:medications?|meds|takes?|taking|renew(?:ed|al)?|refill(?:ed)?|prescri\w+|started on|"
                  r"continues? on|switch(?:ed)? to|treated with|trial of|dose of)\b", re.I)
_BEFORE_SLOT = re.compile(r"(?:\b(?:takes?|taking|include[sd]?|including|are|renew|refill|started on|start|starting|"
                          r"continue|continues on|stop|stopped|switch(?:ed)? to|treated with|trial of|prescribed|"
                          r"prescribe|on)|:)\s*$", re.I)
_LIST_JOIN = re.compile(r"(?:,\s*(?:and\s+)?|\s+and\s+|\s+plus\s+|\s+with\s+)$", re.I)
_SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?](?=\d)[^.!?\n]*)*[.!?]?")      # "5.4" does not end a sentence
_WORD = re.compile(r"[A-Za-z][A-Za-z']*")
_DIGIT_LED = re.compile(r"(?<![\w.])([248])[- ]?([A-Za-z]{4,})\b")
_DIGIT_SOUND = {"2": "to", "4": "for", "8": "ate"}
_FILLER = {"and", "in", "a", "the", "of", "or", "an", "to", "on"}
_TITLE = re.compile(r"\b(?:Dr|Mr|Mrs|Ms|Miss|Mx|Prof)\.?\s*$")
_DOUBLE_UNIT = re.compile(r"(\d)\s?(?:mg|milligrams?)\s+(micrograms?|mcg)\b", re.I)


def load_names(path: Path = DRUG_FILE) -> Tuple[List[str], List[str]]:
    """(names a word may be corrected to, names only protected from change: the "-" lines)."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return [], []
    lines = [ln.strip().lower() for ln in lines if ln.strip() and not ln.startswith("#")]
    return [ln for ln in lines if not ln.startswith("-")], [ln[1:] for ln in lines if ln.startswith("-")]


class DrugNameCorrector:
    """Callable text -> text. Helpers are injected so the rules can be tested without the libraries."""

    def __init__(self, names: Iterable[str], ratio: Callable, phonetic: Callable, zipf: Callable,
                 extract: Optional[Callable] = None, common: Iterable[str] = (), known: Iterable[str] = (),
                 preferred: Iterable[str] = (), brands: Iterable[str] = ()):
        self.ratio, self.phonetic, self.zipf, self._extract = ratio, phonetic, zipf, extract
        # Brand names written in lower case get their capital ("ozempic" -> Ozempic); a brand
        # that is also an everyday word is left alone. Brands are also names a misheard word
        # may be corrected to ("Jardientz 25 mg" -> Jardiance), written with their capital.
        self.brands = {b.lower(): b for b in brands if len(b) >= 4 and b[0].isupper() and self.zipf(b.lower()) < 3.0}
        self.names = sorted({n.lower() for n in names if len(n) >= MIN_LEN}
                            | {b for b in self.brands if len(b) >= MIN_LEN})
        self.name_set: Set[str] = set(self.names)
        self.common = {c.lower() for c in common} & self.name_set
        self.preferred = {p.lower() for p in preferred} & self.name_set
        self._brand_re = (re.compile(r"\b(" + "|".join(sorted(map(re.escape, self.brands), key=len, reverse=True))
                                     + r")\b") if self.brands else None)
        self.known = {k.lower() for k in known} | self.name_set        # words never to change
        self._phon = {n: phonetic(n) for n in self.names}
        self._by_phon = {}
        for n, key in self._phon.items():
            self._by_phon.setdefault(key, []).append(n)
        self.total_corrections = 0

    # ── matching ────────────────────────────────────────────────────────────
    def _ranked(self, word: str) -> List[Tuple[str, float]]:
        """Nearest names: spelling similarity blended with similarity of sound, everyday drugs slightly ahead."""
        if self._extract is not None:
            hits = self._extract(word, self.names, limit=15)
        else:
            hits = sorted(((n, self.ratio(word, n)) for n in self.names), key=lambda x: -x[1])[:15]
        key = self.phonetic(word)
        scored = []
        for n, s in hits:
            blended = (1 - SOUND_WEIGHT) * s + SOUND_WEIGHT * self.ratio(key, self._phon[n])
            bonus = PREFERRED_BONUS if n in self.preferred and blended >= PREFERRED_FLOOR else \
                COMMON_BONUS if n in self.common else 0
            scored.append((n, blended + bonus))
        return sorted(scored, key=lambda x: -x[1])

    def match(self, word: str, slot: bool) -> Optional[str]:
        """Drug name for `word` (letters only, lower case), or None."""
        ranked = self._ranked(word)
        if not ranked:
            return None
        best, score = ranked[0]
        second = next((s for n, s in ranked[1:] if n.rstrip("e") != best.rstrip("e")), 0.0)
        if abs(len(best) - len(word)) > max(3, int(0.4 * len(best))):
            return None
        if score >= ANYWHERE_SCORE and score - second >= SLOT_MARGIN:
            return best
        if not slot:
            return None
        if score >= SLOT_SCORE and score - second >= SLOT_MARGIN:
            return best
        return None

    def sounds_like(self, words: List[str]) -> Optional[str]:
        """Ordinary words that together have exactly one drug name's sound ('ram', 'and', 'pearl')."""
        for kept in ([w for w in words if w not in _FILLER], words):
            joined = "".join(kept)
            if len(kept) < 2 or len(joined) < 6:
                continue
            key = self.phonetic(joined)
            same = self._by_phon.get(key, [])
            if len(key) >= 5 and len(same) == 1 and joined[0] == same[0][0] and self.ratio(joined, same[0]) >= SOUND_SCORE:
                return same[0]
        return None

    # ── text ────────────────────────────────────────────────────────────────
    def _unknown(self, word: str) -> bool:
        w = word.lower().replace("'", "")
        return len(w) >= MIN_LEN and not word.isupper() and w not in self.known and self.zipf(w) < UNKNOWN_ZIPF

    def _is_drug(self, word: str) -> bool:
        return word.lower() in self.name_set

    def _fix_sentence(self, s: str, before_all: str) -> str:
        medication = bool(_CUE.search(s) or re.search(_DOSE, s, re.I) or re.search(_FREQ, s, re.I))
        if medication:
            def digit(m):
                if not _AFTER_SLOT.match(s[m.end():]) and not _LIST_JOIN.search(s[:m.start()]):
                    return m.group(0)
                hit = self.match(_DIGIT_SOUND[m.group(1)] + m.group(2).lower(), slot=True)
                return hit if hit else m.group(0)
            s = _DIGIT_LED.sub(digit, s)
        words = [(m.start(), m.end(), m.group()) for m in _WORD.finditer(s)]
        out, last, i = [], 0, 0
        drug_ends = set()                                   # where a drug name (found or fixed) ended
        while i < len(words):
            fixed = None
            if self._is_drug(words[i][2]):
                drug_ends.add(words[i][1])
            for span in range(min(MAX_SPAN, len(words) - i), 0, -1):
                group = words[i:i + span]
                if any(s[a[1]:b[0]] not in (" ", "-") for a, b in zip(group, group[1:])):
                    continue
                pieces = [g[2] for g in group]
                if any(self._is_drug(p) for p in pieces):
                    continue
                start, end = group[0][0], group[-1][1]
                before, after = s[:start], s[end:]
                if _TITLE.search(before) or _TITLE.search(before_all + before):
                    continue
                dose_next = medication and bool(_AFTER_DOSE.match(after))
                slot = medication and (bool(_AFTER_SLOT.match(after)) or bool(_BEFORE_SLOT.search(before))
                                       or self._after_drug(before, drug_ends))
                lower = [p.lower().replace("'", "") for p in pieces]
                if span > 1 and (lower[0] in _FILLER or lower[-1] in _FILLER):
                    continue                                # "and ___" keeps its "and"
                hit = None
                if any(self._unknown(p) for p in pieces):
                    if span > 1 and any(self.zipf(w) >= 4.5 and w not in _FILLER for w in lower):
                        continue                            # never swallow an ordinary word next to it
                    hit = self.match("".join(w for w in lower if w not in _FILLER or span == 1), slot)
                elif span > 1 and (dose_next or slot):
                    hit = self.sounds_like(lower)           # "Ram and Pearl 5 mg", "dorsal amide"
                if hit:
                    fixed = (start, end, hit)
                    i += span
                    break
            if fixed:
                start, end, hit = fixed
                hit = self.brands.get(hit, hit)
                if self._starts_sentence(s[:start], before_all):
                    hit = hit[0].upper() + hit[1:]
                out.append(s[last:start] + hit)
                last = end
                drug_ends.add(end)
                self.total_corrections += 1
            else:
                i += 1
        return "".join(out) + s[last:]

    @staticmethod
    def _starts_sentence(before: str, before_all: str) -> bool:
        if before.strip():
            return False
        prior = before_all.rstrip()
        return not prior or prior[-1] in ".!?\n"

    @staticmethod
    def _after_drug(before: str, drug_ends: Set[int]) -> bool:
        """Is this the next item of a list whose previous item was a drug ('X 5 mg daily and ___')?"""
        m = _LIST_JOIN.search(before)
        if not m:
            return False
        head = before[:m.start()]
        while True:                                         # step back over the previous drug's dose and frequency
            t = re.search(r"\s*,?\s*(?:" + _DOSE + "|" + _FREQ + r")\s*$", head, re.I)
            if not t or not t.group(0):
                break
            head = head[:t.start()]
        return len(head) in drug_ends

    def __call__(self, text: str) -> str:
        if not self.names or not text:
            return text
        text = _DOUBLE_UNIT.sub(lambda m: m.group(1) + " mcg", text)    # "75 milligrams, micrograms": the second is meant
        if self._brand_re is not None:
            text = self._brand_re.sub(lambda m: self.brands[m.group(1)], text)
        out, pos = [], 0
        for m in _SENTENCE.finditer(text):
            out.append(text[pos:m.start()])
            out.append(self._fix_sentence(m.group(0), text[:m.start()]))
            pos = m.end()
        out.append(text[pos:])
        return "".join(out)


_cached = None


def make_drug_corrector(common: Iterable[str] = (), known: Iterable[str] = (), preferred: Iterable[str] = (),
                        brands: Iterable[str] = ()) -> Optional[DrugNameCorrector]:
    """Corrector with rapidfuzz/jellyfish/wordfreq, or None if they or the name list are missing."""
    try:
        from rapidfuzz import fuzz, process
        import jellyfish
        from wordfreq import zipf_frequency
    except ImportError:
        return None
    names, protected = load_names()
    if not names:
        return None
    known = list(known) + protected

    def extract(word, choices, limit=8):
        return [(c, s) for c, s, _ in process.extract(word, choices, scorer=fuzz.ratio, limit=limit)]

    return DrugNameCorrector(names, ratio=fuzz.ratio, phonetic=jellyfish.metaphone,
                             zipf=lambda w: zipf_frequency(w, "en"), extract=extract, common=common, known=known,
                             preferred=preferred, brands=brands)


def default_corrector() -> Optional[DrugNameCorrector]:
    """One shared corrector: everyday drugs and the words to leave alone come from the vocabulary files."""
    global _cached
    if _cached is None:
        common, known, preferred, brands = [], [], [], []
        try:
            import vocab
            lex = vocab.load_lexicon(env={})
            for t in lex.all_terms():
                words = [w.strip(".,;:()").lower() for w in re.split(r"[\s/\-]+", t.text)]
                known.extend(words)
                if t.category == "drug":
                    common.extend(words)
                    if t.text[:1].isupper() and " " not in t.text:
                        brands.append(t.text)
            meds = vocab.load_medications()
            preferred = vocab.medication_words(meds)
            brands += [m.group(1) for m in (re.search(r"\(([A-Z]\w+)\)", x) for x in meds) if m]
        except Exception:                                   # the list alone is enough to work
            pass
        _cached = make_drug_corrector(common, known, preferred, brands) or False
    return _cached or None


def apply(text: str) -> str:
    corrector = default_corrector()
    return corrector(text) if corrector else text
