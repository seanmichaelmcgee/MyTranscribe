"""text_fixes: spelled-out abbreviations and personal 'heard => correct' rules."""

import pytest

from text_fixes import apply_corrections, join_spelled_letters, load_corrections, make_text_fixes

KNOWN = {"heent", "cva", "snt", "jvp"}


@pytest.mark.parametrize("raw, want", [
    ("H-E-E-N-T normal, TMs clear.", "HEENT normal, TMs clear."),
    ("c-v-a tenderness", "CVA tenderness"),
    ("Abdomen S N T, no guarding.", "Abdomen SNT, no guarding."),
    ("H, E, E, N, T normal.", "HEENT normal."),
    ("Noted C. V. A. tenderness", "Noted CVA tenderness"),
    ("Exam showed J V P. Lungs clear.", "Exam showed JVP. Lungs clear."),
])
def test_join_spelled_letters(raw, want):
    assert join_spelled_letters(raw, KNOWN) == want


@pytest.mark.parametrize("text", [
    "Options A, B, C were discussed.",          # not a known abbreviation -> untouched
    "X-ray of the chest.",                      # not single letters
    "Vitamin B-12 and T-4 levels.",             # letters with digits
    "I saw a B and a C on the chart.",
    "",
])
def test_ordinary_text_untouched(text):
    assert join_spelled_letters(text, KNOWN) == text


def test_corrections_file_rules(tmp_path):
    bundled = tmp_path / "bundled.txt"
    user = tmp_path / "user.txt"
    bundled.write_text("# comment\nanti-Rho => anti-Ro\nfoo bar => baz\n", encoding="utf-8")
    user.write_text("foo bar => qux\nbad line without arrow\n", encoding="utf-8")
    rules = load_corrections([bundled, user, tmp_path / "missing.txt"])
    assert apply_corrections("Her ANA is positive with anti-Rho antibodies.", rules) == \
        "Her ANA is positive with anti-Ro antibodies."
    assert apply_corrections("anti Rho", rules) == "anti-Ro"                 # space/hyphen interchangeable
    assert apply_corrections("Foo  bar.", rules) == "qux."                   # user file wins; case-insensitive
    assert apply_corrections("rhombus foobar", rules) == "rhombus foobar"    # whole words only


def test_make_text_fixes_chain(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("anti-Rho => anti-Ro\n", encoding="utf-8")
    fix = make_text_fixes(KNOWN, correction_files=[f])
    assert fix("H-E-E-N-T normal. Anti-Rho positive.") == "HEENT normal. anti-Ro positive."


def test_bundled_corrections_file_parses():
    from text_fixes import BUNDLED_CORRECTIONS
    rules = load_corrections([BUNDLED_CORRECTIONS])
    assert rules and apply_corrections("anti-Rho", rules) == "anti-Ro"
