"""vocab_correct: fixes near-miss non-words, never touches real words or ambiguous cases."""

import csv
from pathlib import Path

import pytest

pytest.importorskip("rapidfuzz")
pytest.importorskip("jellyfish")
pytest.importorskip("wordfreq")

import vocab
from vocab_correct import TermCorrector, make_corrector

DATA = Path(__file__).parent / "data" / "whisper_misrecognitions.tsv"


@pytest.fixture(scope="module")
def corrector():
    return make_corrector(t.text for t in vocab.load_lexicon(env={}).all_terms())


@pytest.mark.parametrize("heard,expected", [
    ("licenopril", "lisinopril"),
    ("pantaprazola", "pantoprazole"),
    ("semiglutide", "semaglutide"),
    ("Clopidobrel", "Clopidogrel"),            # capitalisation kept
    ("ox carbazapene", "oxcarbazepine"),       # split word re-joined
    ("metaformin", "metformin"),
    ("empaglyflozin", "empagliflozin"),
    ("levothyroxin", "levothyroxine"),
])
def test_fixes_near_misses(corrector, heard, expected):
    assert corrector(heard) == expected


def test_real_clinical_prose_untouched(corrector):
    text = ("Thank you for seeing this 4-year-old boy with recurrent wheeze. He was started on "
            "fluticasone 125 mcg two puffs b.i.d. with an AeroChamber. Hydroxyzine was stopped; "
            "hydralazine continues. Solids introduction discussed. Follow-up in 6 weeks. "
            "Nicker, Lyme, prednisone and PHQ-9 noted. Dr. Okonkwo agrees.")
    assert corrector(text) == text


def test_sound_alike_real_drugs_never_swapped(corrector):
    for real in ("hydroxyzine", "hydralazine", "clonidine", "clonazepam", "celecoxib",
                 "citalopram", "escitalopram", "risperidone", "ropinirole"):
        assert corrector(real) == real


def test_skips_digits_caps_and_short_words(corrector):
    assert corrector("Gave 5mgg of XYZQR to Jnn") == "Gave 5mgg of XYZQR to Jnn"


def test_does_not_merge_ordinary_words(corrector):
    assert corrector("solidos in the plan") == "solidos in the plan"


def test_whisper_misrecognition_regressions(corrector):
    rows = [r for r in csv.DictReader((l for l in DATA.open(encoding="utf-8") if not l.startswith("#")),
                                      delimiter="\t")]
    fixes = [r for r in rows if r["expect"] == "fix"]
    keeps = [r for r in rows if r["expect"] == "keep"]
    assert len(fixes) >= 70 and len(keeps) >= 80
    failed = [(r["heard"], corrector(r["heard"])) for r in fixes
              if r["term"].lower() not in corrector(r["heard"]).lower()]
    assert len(failed) <= 3, failed
    changed = [(r["heard"], corrector(r["heard"])) for r in keeps if corrector(r["heard"]) != r["heard"]]
    assert changed == [], changed


def test_ambiguous_match_left_alone():
    # Two equally close targets -> no change.
    ratio = lambda a, b: 90 if b in ("alphazine", "alphazone") else 10
    c = TermCorrector(["alphazine", "alphazone"], ratio=ratio, phonetic=lambda w: w,
                      zipf=lambda w: 0.0)
    assert c("alphazane") == "alphazane"


def test_counts_but_never_logs_text(corrector, caplog):
    import logging
    caplog.set_level(logging.INFO)
    before = corrector.total_corrections
    corrector("Patient Zebedee takes licenopril")
    assert corrector.total_corrections == before + 1
    assert "Zebedee" not in caplog.text and "licenopril" not in caplog.text


def test_transcriber_applies_pipeline():
    import numpy as np
    from chunked_transcriber import ChunkedTranscriber
    from fakes import ArrayStream, FakeEngine, factory_for, speech_like
    seen = []
    eng = FakeEngine(text_fn=lambda i, a: "started licenopril")
    t = ChunkedTranscriber(eng, "base", stream_factory=factory_for(ArrayStream(speech_like(12))),
                           chunk_target_s=5, prompt_builder=lambda ctx: seen.append(ctx) or f"P[{ctx}]",
                           postprocess=lambda s: s.replace("licenopril", "lisinopril"))
    t.start_recording()
    t._capture_thread.join(5)
    t.stop_recording()
    assert t.wait_until_idle(5)
    assert t.transcriptions[0] == "started lisinopril"
    assert eng.calls[1][1] == "P[started lisinopril]"   # corrected text feeds the next prompt
    assert seen[0] == ""


def test_transcriber_survives_pipeline_errors():
    from chunked_transcriber import ChunkedTranscriber
    from fakes import ArrayStream, FakeEngine, factory_for, speech_like

    def boom(_):
        raise ValueError("bad vocab file")
    eng = FakeEngine(text_fn=lambda i, a: "text")
    t = ChunkedTranscriber(eng, "base", stream_factory=factory_for(ArrayStream(speech_like(3))),
                           prompt_builder=boom, postprocess=boom)
    t.start_recording()
    t._capture_thread.join(5)
    t.stop_recording()
    assert t.wait_until_idle(5)
    assert t.transcriptions == ["text"] and eng.calls[0][1] == "base"
