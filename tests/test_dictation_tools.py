"""eval_metrics scoring + make_test_dictation templates and mic simulation."""

import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import make_test_dictation as mtd
from eval_metrics import normalize_words, term_hits, word_error_rate
from vocab import load_lexicon


def test_normalize_units_and_numbers():
    assert normalize_words("Apixaban 5 milligrams twice daily, 8.4 percent!") == \
        ["apixaban", "5", "mg", "twice", "daily", "8", "4", "%"]
    assert normalize_words("apixaban five mg") == normalize_words("Apixaban 5mg")


def test_wer():
    assert word_error_rate("the cat sat", "the cat sat") == (0.0, 3)
    assert word_error_rate("the cat sat", "the bat sat")[0] == pytest.approx(1 / 3)
    assert word_error_rate("a b", "")[0] == 1.0
    assert word_error_rate("", "x")[1] == 0


def test_align_ops():
    from eval_metrics import align
    ops = align("a b c d".split(), "a x c e d".split())
    assert [o[0] for o in ops] == ["ok", "sub", "ok", "ins", "ok"]
    assert align([], ["x"]) == [("ins", None, 0)] and align(["x"], []) == [("del", 0, None)]


def test_breakdown_names_free_medical_common_invented():
    from eval_metrics import breakdown
    zipf = {"shows": 4.5, "sinus": 3.3, "rhythm": 4.0, "psoas": 1.9, "troponin": 2.1, "and": 7.0,
            "was": 7.0, "negative": 4.6, "interponem": 0.0, "ecg": 2.0}.get
    medical = {"sinus", "troponin", "ecg"}.__contains__
    b = breakdown("Dear Dr. Haddad, ECG shows sinus rhythm and troponin was negative.",
                  "Dear Dr. Hadad Smith, ECG psoas sinus rhythm interponem was negative.",
                  names=["Haddad"], is_medical=medical, zipf=lambda w: zipf(w, 5.0))
    # "Hadad Smith" for "Haddad": free (name). "psoas" for "shows", "interponem" for "and troponin".
    assert b.words == 9                              # "dear" + 8 words; dr/haddad excluded
    assert b.errors == 3                             # shows->psoas, and->interponem, troponin dropped
    assert b.medical == 3 and b.medical_errors == 1 and b.medical_missed == ["troponin"]
    assert b.common_errors == 2                      # shows, and
    assert sorted(b.invented) == ["interponem", "psoas"]
    r = b.rates()
    assert r["medical_wer"] == 33.3 and r["invented_per_100"] == 22.2


def test_load_medical_words(tmp_path):
    from eval_metrics import load_medical_words
    p = tmp_path / "v.txt"
    p.write_text("# comment\n## exam | abdomen, tender\nabbr: SNT, HEENT\nother: soft non-tender, chest\n",
                 encoding="utf-8")
    zipf = {"abdomen": 3.6, "tender": 3.9, "snt": 1.8, "heent": 0.0, "soft": 4.6, "non": 4.0,
            "chest": 4.5}.get
    words = load_medical_words([p], zipf=lambda w: zipf(w, 5.0))
    assert words == {"abdomen", "tender", "snt", "heent"}


def test_term_hits_ignores_case_hyphen_space():
    found, missed = term_hits(["Trelegy Ellipta", "DTaP-IPV-Hib", "apixaban", "HbA1c"],
                              "switched to trelegy ellipta; given DTaP IPV Hib; HbA1c 7")
    assert found == ["Trelegy Ellipta", "DTaP-IPV-Hib", "HbA1c"] and missed == ["apixaban"]


@pytest.fixture(scope="module")
def lex():
    return load_lexicon(env={})


@pytest.mark.parametrize("name", sorted(mtd.TEMPLATES))
def test_templates_fill_completely(lex, name):
    for seed in range(5):
        text, terms = mtd.fill_template(mtd.TEMPLATES[name], lex, random.Random(seed))
        assert "{" not in text and "}" not in text
        assert len(terms) >= 4 and len(set(t.lower() for t in terms)) == len(terms)
        assert all(t.lower() in text.lower() for t in terms)
        assert not any(s[0].islower() for s in text.split(". ")[1:] if s)   # sentences capitalised


def test_topic_slot_draws_from_vocabulary(lex):
    text, terms = mtd.fill_template("on {hypertension:drug}.", lex, random.Random(0))
    assert terms[0] in {t.text for t in lex.topics["hypertension"].terms if t.category == "drug"}


def test_templates_mostly_use_vocabulary_terms(lex):
    vocab_terms = {t.text.lower() for t in lex.all_terms()}
    picks = []
    for name in mtd.TEMPLATES:
        _, terms = mtd.fill_template(mtd.TEMPLATES[name], lex, random.Random(3))
        picks += terms
    in_vocab = [t for t in picks if t.lower() in vocab_terms]
    assert len(in_vocab) / len(picks) > 0.9, sorted(set(picks) - set(in_vocab))


def tone(seconds=2.0):
    t = np.arange(int(16000 * seconds)) / 16000
    x = (0.3 * np.sin(2 * np.pi * 220 * t) * (np.sin(2 * np.pi * 2 * t) > 0)).astype(np.float32)
    return x


@pytest.mark.parametrize("profile", mtd.PROFILES)
def test_profiles_are_valid_audio(profile):
    x = tone()
    y = mtd.apply_profile(x, profile, seed=1, babble_sources=[tone(1.0)])
    assert y.shape == x.shape and y.dtype == np.float32
    assert np.isfinite(y).all() and np.max(np.abs(y)) <= 0.951
    assert np.all(mtd.apply_profile(x, profile, seed=1, babble_sources=[tone(1.0)]) == y)  # deterministic


def test_conference_profile_adds_reverb_and_noise():
    x = tone()
    clean = mtd.apply_profile(x, "clean", seed=1)
    conf = mtd.apply_profile(x, "conference", seed=1)
    gaps = x == 0
    # Energy appears in the silent gaps (reverb tail + noise) only for the far-field mic.
    assert np.sqrt(np.mean(clean[gaps] ** 2)) < 1e-6 < np.sqrt(np.mean(conf[gaps] ** 2))


def test_wav_roundtrip_and_resample(tmp_path):
    x = tone(0.5)
    p = tmp_path / "a.wav"
    mtd.write_wav(p, x)
    y, sr = mtd.read_wav(p)
    assert sr == 16000 and np.allclose(x, y, atol=1e-4)
    assert len(mtd.resample(x, 16000, 22050)) == int(round(len(x) * 22050 / 16000))
