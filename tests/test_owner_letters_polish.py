"""Fixes from the owner's dictated letters of 2026-11-17 (fictional text)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import vocab  # noqa: E402
import voice_commands as vc  # noqa: E402
from text_fixes import format_readings, make_text_fixes  # noqa: E402

pytest.importorskip("rapidfuzz")
pytest.importorskip("wordfreq")
import drug_names  # noqa: E402


def dictated(raw):
    return vc.apply(raw, lenient=True, punctuation=True, only_dictated_commas=True)


# ── punctuation polish ───────────────────────────────────────────────────────
@pytest.mark.parametrize("raw, want", [
    ("For the last 6 months it turns out, comma. It was quite intermittent, period.",
     "For the last 6 months it turns out, it was quite intermittent."),
    ("She would get a sharp pain, comma. This was very intermittent, period.",
     "She would get a sharp pain, this was very intermittent."),
    ("Seen by, comma, Dr. Patel, comma. ECG was normal, comma. I reviewed it, period.",
     "Seen by, Dr. Patel, ECG was normal, I reviewed it."),
    ("Started, comma. Ozempic was added, period.", "Started, Ozempic was added."),
])
def test_no_capital_after_a_dictated_comma(raw, want):
    assert dictated(raw) == want


@pytest.mark.parametrize("raw, want", [
    ("She did not tolerate... dulaglutide because of nausea, period.",
     "She did not tolerate dulaglutide because of nausea."),
    ("I... should note that, period.", "I should note that."),
    ("I wonder if... Perhaps not, period.", "I wonder if... Perhaps not."),
])
def test_hesitation_dots_dropped_when_marks_are_dictated(raw, want):
    assert dictated(raw) == want


def test_hesitation_dots_kept_without_dictated_marks():
    assert vc.apply("She did not tolerate... dulaglutide.", lenient=True) == "She did not tolerate... dulaglutide."


@pytest.mark.parametrize("raw, want", [
    ("I've been reluctant to start insulin.", "I have been reluctant to start insulin."),
    ("We've stopped it.", "We have stopped it."),
    ("30-pack year smoking history.", "30-pack-year smoking history."),
    ("Hypertension on three agents.", "Hypertension on 3 agents."),
])
def test_written_as_said(raw, want):
    assert format_readings(raw) == want


def test_correction_rules_keep_a_capital_when_the_word_is_kept():
    fix = make_text_fixes(set())
    assert fix("Labs as follows, medications is below, C attached.") == \
        "Labs as follows, medications as below, see attached."
    assert fix("Medications is below.") == "Medications as below."


# ── usual medications ────────────────────────────────────────────────────────
def test_medications_file_parsing(tmp_path):
    f = tmp_path / "my_medications.txt"
    f.write_text("# comment\nbisoprolol\nempagliflozin (Jardiance)\nbisoprolol\n\n", encoding="utf-8")
    meds = vocab.load_medications(env={}, paths=[tmp_path / "missing.txt", f])
    assert meds == ["bisoprolol", "empagliflozin (Jardiance)"]
    assert vocab.medication_words(meds) == {"bisoprolol", "empagliflozin", "jardiance"}
    assert vocab.load_medications(env={"MYTRANSCRIBE_MEDICATIONS": "off"}, paths=[f]) == []


def test_bundled_medications_list_exists():
    assert "bisoprolol" in vocab.load_medications(env={}, paths=[vocab.BUNDLED_MEDICATIONS])


STYLE = "Dear Dr. Patel, Thank you for seeing Mrs. Jones. The chest is clear, period. New paragraph."


def _builder(meds, budget=80):
    lex = vocab.parse_lexicon_text("## core | letter\nother: follow-up\n")
    return vocab.PromptBuilder(STYLE, lex, count=lambda t: len(t.split()), budget=budget, medications=meds)


def test_medications_never_push_out_the_style_example():
    b = _builder([f"drug{i}" for i in range(60)], budget=40)
    p = b("")
    assert p.startswith(STYLE)
    assert len(p.split()) <= 40
    assert "Usual medications: drug0," in p


def test_medications_rotate_and_restart_with_each_dictation():
    b = _builder([f"drug{i}" for i in range(60)], budget=40)
    first = b("")
    second = b("He was seen today.")
    assert first != second and "drug0" not in second
    assert b("") == first                     # a new dictation starts from the top again


def test_medications_already_said_are_not_repeated():
    b = _builder(["bisoprolol", "gliclazide (Diamicron)"])
    p = b("She takes gliclazide daily.")
    assert "Usual medications: bisoprolol." in p
    assert "Diamicron" not in b("")           # brands are left out of the prompt


# ── drug names ───────────────────────────────────────────────────────────────
def test_brand_names_get_their_capital():
    assert drug_names.apply("Also ozempic weekly and jardiance daily.") == "Also Ozempic weekly and Jardiance daily."


def test_misheard_usual_medication_in_a_drug_position():
    assert drug_names.apply("She takes metformin and glicoside 60 mg daily.") == \
        "She takes metformin and gliclazide 60 mg daily."


def test_a_close_call_goes_to_a_real_drug():
    assert drug_names.apply("He takes teotroprim once daily, apixaban 5 mg twice daily.") == \
        "He takes tiotropium once daily, apixaban 5 mg twice daily."
