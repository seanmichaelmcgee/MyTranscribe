"""CTC probability merging and ARPA backoff, independent of model/audio data."""
import itertools
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from asr_trial_common import MODEL_REVISION, sha256
from medasr_ctc_decoder import ArpaLanguageModel, prefix_beam_search
from prepare_medasr_lm import LM_SHA256


def exhaustive_best(probabilities):
    totals = defaultdict(float)
    for path in itertools.product(range(probabilities.shape[1]), repeat=probabilities.shape[0]):
        collapsed, last = [], None
        for token in path:
            if token != last and token != 0:
                collapsed.append(token)
            last = token
        totals[tuple(collapsed)] += math.prod(probabilities[t, token] for t, token in enumerate(path))
    return list(max(totals, key=totals.get))


def test_prefix_merges_paths_instead_of_choosing_best_path():
    probabilities = np.array([[.40, .35, .25], [.45, .30, .25]])
    assert prefix_beam_search(np.log(probabilities), 64, 3, -100) == exhaustive_best(probabilities)


def test_repeated_tokens_require_intervening_blank():
    assert prefix_beam_search(np.log([[.01, .99], [.01, .99]]), 8, 2) == [1]
    assert prefix_beam_search(np.log([[.01, .99], [.99, .01], [.01, .99]]), 8, 2) == [1, 1]


def test_random_small_search_matches_exhaustive_ctc():
    rng = np.random.default_rng(52)
    for _ in range(20):
        p = rng.uniform(.1, 1, (4, 3))
        p /= p.sum(axis=1, keepdims=True)
        assert prefix_beam_search(np.log(p), 64, 3, -100) == exhaustive_best(p)


def test_lm_weight_can_choose_supported_alternative():
    class ToyLM:
        def score(self, history, piece):
            return -8 if piece == "unlikely" else 0
    assert prefix_beam_search(np.log([[.01, .54, .45]]), 8, 3,
        lm=ToyLM(), pieces=["", "unlikely", "supported"], alpha=.5) == [2]


def test_backoff_adds_context_penalty_and_uses_log10(tmp_path):
    path = tmp_path / "lm.sqlite"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE grams (key TEXT PRIMARY KEY, probability REAL, backoff REAL)")
    db.executemany("INSERT INTO grams VALUES (?,?,?)", [("<unk>", -5, 0), ("a", -2, -.3), ("b", -1, 0), ("a b", -.1, 0)])
    db.commit()
    db.close()
    path.with_suffix(".integrity.json").write_text(json.dumps(dict(arpa_sha256=LM_SHA256,
        revision=MODEL_REVISION, index_sha256=sha256(path))), encoding="utf-8")
    lm = ArpaLanguageModel(path)
    try:
        assert lm.score(("a",), "b") == pytest.approx(-.1 * math.log(10))
        assert lm.score(("a",), "missing") == pytest.approx(-5.3 * math.log(10))
    finally:
        lm.close()


def test_invalid_logits_are_rejected():
    with pytest.raises(ValueError):
        prefix_beam_search([[float("nan"), 1]])
    with pytest.raises(ValueError):
        prefix_beam_search([[0, 1]], beam_width=0)
