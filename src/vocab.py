"""
vocab.py — topic-aware vocabulary prompts for Whisper.

Whisper only reads the last ~223 tokens of its prompt, and medical terms cost
~3 characters per token, so the full vocabulary (thousands of tokens) can
never fit. Instead, for every ~30 s chunk we build a fresh prompt:

    <style example> <terms for the topics you are dictating about> <last words said>

Topics come from vocab/primary_care.txt (plus any files you add via
$MYTRANSCRIBE_VOCAB_FILES). A topic switches on when its trigger words or its
terms appear in the recent transcript; "core" is always on. Terms already in
the recent transcript are skipped (they're in the prompt anyway), and the
selection rotates chunk to chunk so a long letter on one topic cycles through
that topic's whole list.
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("vocab")

VOCAB_DIR = Path(__file__).parent / "vocab"
DEFAULT_LEXICON_FILES = (VOCAB_DIR / "primary_care.txt",)
CORRECTION_ONLY_FILES = (VOCAB_DIR / "telnyx_medical_terms.txt",)

PROMPT_TOKEN_BUDGET = 215       # whisper keeps 223; leave a little slack
CONTEXT_TAIL_CHARS = 160        # recent transcript appended at the end
CONTEXT_SCAN_CHARS = 800        # how far back to look for topic triggers
MAX_ACTIVE_TOPICS = 3
CHARS_PER_TOKEN_ESTIMATE = 2.8  # measured 3.0 on this vocabulary; be conservative

# Categories in priority order: hard-to-spell words first.
CATEGORY_PRIORITY = {"drug": 0, "vax": 0, "abbr": 1, "lab": 2, "test": 2, "dx": 3, "other": 4}

_BRAND_RE = re.compile(r"^(?P<term>.+?)\s*\((?P<brand>[A-Z][^)]*)\)\s*$")


@dataclass
class Term:
    text: str
    category: str
    topic: str


@dataclass
class Topic:
    name: str
    triggers: List[str] = field(default_factory=list)
    terms: List[Term] = field(default_factory=list)


@dataclass
class Lexicon:
    topics: Dict[str, Topic] = field(default_factory=dict)
    extra_terms: List[Term] = field(default_factory=list)   # correction-only

    def all_terms(self) -> List[Term]:
        out = [t for topic in self.topics.values() for t in topic.terms]
        return out + self.extra_terms


# ── Parsing ──────────────────────────────────────────────────────────────────
def _split_terms(body: str) -> List[str]:
    """Split a comma list, ignoring commas inside parentheses."""
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def parse_lexicon_text(text: str, lexicon: Optional[Lexicon] = None) -> Lexicon:
    """
    Parse the primary_care.txt format (see that file's header). Topics with
    the same name in several files are merged. "term (Brand)" yields both.
    """
    lex = lexicon or Lexicon()
    topic: Optional[Topic] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("##")):
            continue
        if line.startswith("##"):
            name, _, trig = line[2:].partition("|")
            name = name.strip().lower()
            topic = lex.topics.setdefault(name, Topic(name))
            topic.triggers += [t.strip().lower() for t in trig.split(",") if t.strip()]
            continue
        if topic is None or ":" not in line:
            continue
        category, _, body = line.partition(":")
        category = category.strip().lower()
        seen = {t.text.lower() for t in topic.terms}
        for item in _split_terms(body):
            m = _BRAND_RE.match(item)
            names = [m.group("term"), m.group("brand")] if m else [item]
            for name in names:
                if name.lower() not in seen:
                    topic.terms.append(Term(name, category, topic.name))
                    seen.add(name.lower())
    return lex


def parse_tsv_terms(text: str) -> List[Term]:
    """category<TAB>term lines (telnyx_medical_terms.txt)."""
    out = []
    for line in text.splitlines():
        if not line.strip() or line.startswith("#") or "\t" not in line:
            continue
        cat, term = line.split("\t", 1)
        out.append(Term(term.strip(), cat.strip().lower(), "_correction"))
    return out


def load_lexicon(files: Optional[Iterable[Path]] = None, env: Optional[dict] = None,
                 correction_files: Iterable[Path] = CORRECTION_ONLY_FILES) -> Lexicon:
    """
    Load bundled + user vocabulary. $MYTRANSCRIBE_VOCAB_FILES adds files
    (os.pathsep-separated) in the same format; missing files are logged and skipped.
    """
    env = os.environ if env is None else env
    paths = list(files) if files is not None else list(DEFAULT_LEXICON_FILES)
    extra = env.get("MYTRANSCRIBE_VOCAB_FILES", "")
    paths += [Path(p) for p in extra.split(os.pathsep) if p.strip()]
    lex = Lexicon()
    for p in paths:
        try:
            parse_lexicon_text(Path(p).read_text(encoding="utf-8"), lex)
        except OSError as exc:
            logger.error("Vocabulary file %s unreadable: %s", p, exc)
    for p in correction_files:
        try:
            lex.extra_terms += parse_tsv_terms(Path(p).read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning("Correction vocabulary %s unreadable: %s", p, exc)
    logger.info("Vocabulary: %d topics, %d prompt terms, %d correction-only terms",
                len(lex.topics), sum(len(t.terms) for t in lex.topics.values()), len(lex.extra_terms))
    return lex


# ── Prompt building ──────────────────────────────────────────────────────────
def _contains(haystack: str, needle: str) -> bool:
    """Whole-word, case-insensitive containment (haystack already lower-cased)."""
    return re.search(r"(?<![a-z0-9])" + re.escape(needle.lower()) + r"(?![a-z0-9])", haystack) is not None


def score_topics(lex: Lexicon, context: str) -> List[Tuple[str, float]]:
    """Topics ranked by evidence in the recent transcript (trigger hits + 2x term hits)."""
    ctx = context[-CONTEXT_SCAN_CHARS:].lower()
    scores = []
    for name, topic in lex.topics.items():
        if name == "core" or not ctx:
            continue
        s = sum(1.0 for trig in topic.triggers if _contains(ctx, trig))
        s += sum(2.0 for term in topic.terms if len(term.text) > 3 and _contains(ctx, term.text))
        if s > 0:
            scores.append((name, s))
    scores.sort(key=lambda kv: -kv[1])
    return scores


def estimate_tokens(text: str) -> int:
    return int(len(text) / CHARS_PER_TOKEN_ESTIMATE) + 1


class PromptBuilder:
    """
    Callable: context (transcript so far) -> prompt string for the next chunk.

    style      short example text in your letter style (prompts/medical_prompt.txt)
    lexicon    parsed vocabulary
    count      token counter; pass the engine's exact one when available
    is_common  optional word -> bool; very common phrases ("car seat") are
               skipped because Whisper already spells them right
    """

    def __init__(self, style: str, lexicon: Lexicon,
                 count: Optional[Callable[[str], int]] = None,
                 is_common: Optional[Callable[[str], bool]] = None,
                 budget: int = PROMPT_TOKEN_BUDGET,
                 default_topics: Iterable[str] = ()) -> None:
        self.style = style.strip()
        self.lexicon = lexicon
        self.count = count or estimate_tokens
        self.is_common = is_common or (lambda term: False)
        self.budget = budget
        self.default_topics = list(default_topics)
        self._rotation: Dict[str, int] = {}
        self.last_topics: List[str] = []     # for logging/tests

    def _ordered_terms(self, topic: Topic) -> List[Term]:
        terms = [t for t in topic.terms if not self.is_common(t.text)]
        terms.sort(key=lambda t: CATEGORY_PRIORITY.get(t.category, 5))   # stable: file order within category
        return terms

    def _pick_topics(self, context: str) -> List[str]:
        """
        Topics detected in what was just said (or the user's default topics).

        Nothing detected -> no topics, and the prompt carries no term list at all.
        A list sampled from every topic is all distractors for the words actually
        spoken, and measurably hurt short snippets on real recordings (2026-10-03:
        medical-word errors 8.2 % with the generic list vs 7.2 % without; the
        research says list words that aren't said get inserted). Lists only help
        once the topic is known (drug-heavy letters: 3.5 vs 5.6 %).
        """
        ranked = [name for name, _ in score_topics(self.lexicon, context)][:MAX_ACTIVE_TOPICS]
        if not ranked:
            ranked = [t for t in self.default_topics if t in self.lexicon.topics]
        return ranked

    def __call__(self, context: str) -> str:
        tail = context[-CONTEXT_TAIL_CHARS:].strip() if context else ""
        if tail and len(context) > CONTEXT_TAIL_CHARS:
            space = tail.find(" ")
            if 0 <= space < 30:
                tail = tail[space + 1:]
        recent = context[-CONTEXT_SCAN_CHARS:].lower() if context else ""

        fixed = " ".join(p for p in (self.style, tail) if p)
        remaining = self.budget - self.count(fixed + " Vocabulary: .") - 2
        topics = self._pick_topics(context)
        self.last_topics = topics
        if not topics:
            return fixed                       # no known topic yet: style example + recent text only

        # Round-robin across topics (rotating start point per topic), then core.
        queues = []
        for name in topics:
            terms = [t for t in self._ordered_terms(self.lexicon.topics[name]) if not _contains(recent, t.text)]
            if terms:
                start = self._rotation.get(name, 0) % len(terms)
                queues.append((name, terms[start:] + terms[:start]))
        core = self.lexicon.topics.get("core")
        if core:
            queues.append(("core", [t for t in self._ordered_terms(core) if not _contains(recent, t.text)]))

        chosen: List[str] = []
        used = {name: 0 for name, _ in queues}
        while remaining > 0 and any(q for _, q in queues):
            progressed = False
            for name, q in queues:
                if not q:
                    continue
                term = q.pop(0)
                cost = self.count(", " + term.text)
                if cost <= remaining:
                    chosen.append(term.text)
                    remaining -= cost
                    used[name] += 1
                    progressed = True
            if not progressed:
                break
        for name, n in used.items():
            self._rotation[name] = self._rotation.get(name, 0) + n

        vocab = ("Vocabulary: " + ", ".join(chosen) + ".") if chosen else ""
        prompt = " ".join(p for p in (self.style, vocab, tail) if p)
        return prompt


def make_wordfreq_is_common(threshold: float = 4.0) -> Optional[Callable[[str], bool]]:
    """Term is 'common' if every word in it has Zipf frequency >= threshold. None if wordfreq missing."""
    try:
        from wordfreq import zipf_frequency
    except ImportError:
        return None

    def is_common(term: str) -> bool:
        words = re.findall(r"[A-Za-z]+", term)
        return bool(words) and all(zipf_frequency(w, "en") >= threshold for w in words)
    return is_common


class PostProcess:
    """Chunk post-processing chain: spelling corrector, then text_fixes (letters, personal rules)."""

    def __init__(self, corrector=None, fixes: Optional[Callable[[str], str]] = None):
        self.corrector, self.fixes = corrector, fixes

    @property
    def total_corrections(self) -> int:
        return getattr(self.corrector, "total_corrections", 0)

    def suspicious(self, text: str) -> List[str]:
        """Words to flag for checking (non-words the corrector wouldn't guess at)."""
        return self.corrector.suspicious(text) if self.corrector is not None else []

    def __call__(self, text: str) -> str:
        if self.corrector is not None:
            text = self.corrector(text)
        if self.fixes is not None:
            text = self.fixes(text)
        return text


def known_abbreviations(lex: Lexicon) -> set:
    """Abbreviations from the vocabulary (for joining spelled-out letters)."""
    out = set()
    for t in lex.all_terms():
        for w in re.split(r"[\s,/]+", t.text):
            w = w.strip(".()")
            if 2 <= len(w) <= 8 and w.isalpha() and (t.category == "abbr" or w.isupper()):
                out.add(w.lower())
    return out


def build_text_pipeline(style: str, count: Optional[Callable[[str], int]] = None,
                        env: Optional[dict] = None, correction_files: Optional[Iterable[Path]] = None):
    """
    Returns (prompt_builder_or_None, postprocess_or_None) according to env:
      MYTRANSCRIBE_VOCAB=off        -> no topic prompts (static prompt only)
      MYTRANSCRIBE_AUTOCORRECT=off  -> no spelling correction / text fixes
      MYTRANSCRIBE_VOCAB_FILES      -> extra vocabulary files
      MYTRANSCRIBE_VOCAB_TOPICS     -> comma list of topics to assume before anything is said
    postprocess = spelling corrector + text_fixes (spelled-out abbreviations, personal
    "heard => correct" rules); it exposes .total_corrections like the corrector.
    """
    env = os.environ if env is None else env
    off = lambda name: env.get(name, "").strip().lower() in ("0", "off", "false", "no")
    if off("MYTRANSCRIBE_VOCAB") and off("MYTRANSCRIBE_AUTOCORRECT"):
        return None, None
    lex = load_lexicon(env=env)
    builder = None
    if not off("MYTRANSCRIBE_VOCAB"):
        defaults = [t.strip().lower() for t in env.get("MYTRANSCRIBE_VOCAB_TOPICS", "").split(",") if t.strip()]
        builder = PromptBuilder(style, lex, count=count, is_common=make_wordfreq_is_common(),
                                default_topics=defaults)
    post = None
    if not off("MYTRANSCRIBE_AUTOCORRECT"):
        from vocab_correct import make_corrector
        from text_fixes import make_text_fixes
        post = PostProcess(make_corrector(t.text for t in lex.all_terms()),
                           make_text_fixes(known_abbreviations(lex), correction_files))
    return builder, post
