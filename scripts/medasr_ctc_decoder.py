"""Experimental CTC prefix beam search with optional official sentencepiece LM.

Trial code only: no imports from the production GUI, no downloads, no prompt or
reference input. Blank/repeat probabilities are merged before prefix pruning.
"""
import functools
import json
import math
import sqlite3

import numpy as np

from asr_trial_common import MODEL_REVISION, sha256
from prepare_medasr_lm import LM_SHA256

NEG_INF = float("-inf")


def log_add(a, b):
    if a == NEG_INF:
        return b
    if b == NEG_INF:
        return a
    hi, lo = (a, b) if a >= b else (b, a)
    return hi + math.log1p(math.exp(lo - hi))


class ArpaLanguageModel:
    """Bounded-cache read-only SQLite ARPA backoff lookup, in natural logs."""
    def __init__(self, path):
        record = json.loads(path.with_suffix(".integrity.json").read_text(encoding="utf-8"))
        if (record.get("arpa_sha256") != LM_SHA256 or record.get("revision") != MODEL_REVISION
                or record.get("index_sha256") != sha256(path)):
            raise ValueError("Language model provenance mismatch")
        # sqlite extensions are not enabled; parameterized lookups only.
        self.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True,
                                  check_same_thread=False)
        self.db.execute("PRAGMA mmap_size=1073741824")
        self.lookup = functools.lru_cache(maxsize=200000)(self._lookup)
        self.score = functools.lru_cache(maxsize=200000)(self._score)

    def _lookup(self, words):
        return self.db.execute("SELECT probability, backoff FROM grams WHERE key=?",
                               (" ".join(words),)).fetchone()

    def _score(self, history, piece):
        history = history[-5:]
        backoff = 0.0
        for size in range(len(history), -1, -1):
            context = history[-size:] if size else ()
            match = self.lookup(context + (piece,))
            if match is not None:
                return (backoff + match[0]) * math.log(10)
            if size:
                context_match = self.lookup(context)
                if context_match:
                    backoff += context_match[1]
        unknown = self.lookup(("<unk>",))
        return (backoff + (unknown[0] if unknown else -100.0)) * math.log(10)

    def close(self):
        self.db.close()


def prefix_beam_search(logits, beam_width=8, token_limit=16, token_logp=-8.0,
                       lm=None, pieces=None, alpha=0.0, beta=0.0, blank=0):
    """Return collapsed token IDs; optional LM weights apply once per new piece.

    This is a bounded prefix-beam experiment, not a claim of equivalence to
    Google's pyctcdecode search. Token pruning and beam width are recorded.
    """
    logits = np.asarray(logits)
    if logits.ndim != 2 or not np.isfinite(logits).all():
        raise ValueError("Expected finite frame-by-token logits")
    if beam_width < 1 or token_limit < 1 or not 0 <= blank < logits.shape[1]:
        raise ValueError("Invalid beam/token/blank configuration")
    if lm is not None and (pieces is None or len(pieces) != logits.shape[1]):
        raise ValueError("LM needs the exact indexed tokenizer vocabulary")
    if not all(math.isfinite(x) for x in (alpha, beta, token_logp)) or alpha < 0:
        raise ValueError("Invalid search weights")
    x = logits.astype(np.float64)
    x -= x.max(axis=1, keepdims=True)
    x -= np.log(np.exp(x).sum(axis=1, keepdims=True))
    # prefix -> blank probability, nonblank probability, cumulative LM logprob
    beams = {(): (0.0, NEG_INF, 0.0)}
    for frame in x:
        count = min(token_limit, len(frame))
        candidates = np.argpartition(frame, -count)[-count:]
        candidates = [int(i) for i in candidates if frame[i] >= token_logp or i == blank]
        if blank not in candidates:
            candidates.append(blank)
        next_beams = {}

        def merge(prefix, pb=NEG_INF, pnb=NEG_INF, lm_score=0.0):
            old = next_beams.get(prefix, (NEG_INF, NEG_INF, lm_score))
            next_beams[prefix] = (log_add(old[0], pb), log_add(old[1], pnb), lm_score)

        for prefix, (pb, pnb, lm_score) in beams.items():
            total = log_add(pb, pnb)
            for token in candidates:
                p = float(frame[token])
                if token == blank:
                    merge(prefix, pb=total + p, lm_score=lm_score)
                    continue
                if prefix and token == prefix[-1]:
                    merge(prefix, pnb=pnb + p, lm_score=lm_score)
                    acoustic = pb + p
                else:
                    acoustic = total + p
                if acoustic == NEG_INF:
                    continue
                new_prefix = prefix + (token,)
                new_lm = lm_score
                if lm is not None:
                    context = tuple(pieces[i] for i in prefix[-5:])
                    if len(prefix) < 5:
                        context = ("<s>",) + context
                    new_lm += lm.score(context, pieces[token])
                merge(new_prefix, pnb=acoustic, lm_score=new_lm)
        rank = lambda item: log_add(item[1][0], item[1][1]) + alpha * item[1][2] + beta * len(item[0])
        beams = dict(sorted(next_beams.items(), key=rank, reverse=True)[:beam_width])
    def final_rank(item):
        prefix, (pb, pnb, lm_score) = item
        if lm is not None and (not prefix or pieces[prefix[-1]] != "</s>"):
            history = tuple(pieces[i] for i in prefix[-5:])
            if len(prefix) < 5:
                history = ("<s>",) + history
            lm_score += lm.score(history, "</s>")
        return log_add(pb, pnb) + alpha * lm_score + beta * len(prefix)
    return list(max(beams.items(), key=final_rank)[0])
