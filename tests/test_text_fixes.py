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


@pytest.mark.parametrize("heard, want", [
    ("He was seen in eMERG yesterday.", "He was seen in emerg yesterday."),
    ("Emerg visit on Monday.", "Emerg visit on Monday."),          # a sentence start keeps its capital
    ("Seen in emerg.", "Seen in emerg."),
    ("Emergency department.", "Emergency department."),         # whole words only
])
def test_emerg_is_written_as_dictated(heard, want):
    from text_fixes import BUNDLED_CORRECTIONS
    assert apply_corrections(heard, load_corrections([BUNDLED_CORRECTIONS])) == want


@pytest.mark.parametrize("heard, want", [
    ("He scored 21 out of 30 on the mocha today.", "He scored 21 out of 30 on the MoCA today."),
    ("Her MOCA score was 24.", "Her MoCA score was 24."),
    ("He had a mocha at the café.", "He had a mocha at the café."),       # the drink stays
    ("FEV1 FVC 0.62 after bronchodilator.", "FEV1/FVC 0.62 after bronchodilator."),
    ("FEV1 over FVC ratio is 0.65.", "FEV1/FVC ratio is 0.65."),
])
def test_bundled_vocabulary_fixes(heard, want):
    from text_fixes import BUNDLED_CORRECTIONS
    assert apply_corrections(heard, load_corrections([BUNDLED_CORRECTIONS])) == want


# ── Hesitations, self-corrections, signs and units ───────────────────────────
@pytest.mark.parametrize("raw, want", [
    ("a 58-year-old man with, um, 2 months of heartburn.", "a 58-year-old man with 2 months of heartburn."),
    ("Um, the chest is clear. Uh, he has no fever.", "The chest is clear. He has no fever."),
    ("The chest is clear. Um. He has no fever.", "The chest is clear. He has no fever."),
    ("He drinks, uh.", "He drinks."),
    ("Plan, uh: stop the doxazosin.", "Plan: stop the doxazosin."),
    ("Diabetes, um\nHypertension", "Diabetes\nHypertension"),
    ("Er, eGFR is 58.", "eGFR is 58."),                                # no capital forced onto eGFR
    ("um", ""),
])
def test_hesitations_are_removed(raw, want):
    from text_fixes import remove_fillers
    assert remove_fillers(raw) == want


@pytest.mark.parametrize("text", [
    "He was seen in the ER yesterday.",          # the emergency room, not a hesitation
    "A 3 mm nodule in the right upper lobe.",    # millimetres
    "She said uh-huh when asked.",
    "Ummah Street clinic.",
])
def test_words_that_look_like_hesitations_stay(text):
    from text_fixes import remove_fillers
    assert remove_fillers(text) == text


def test_hesitations_come_out_even_without_extra_corrections():
    from text_fixes import finish
    assert finish("No fever, um, no cough. 1 gram daily.", extra_fixes=False) == "No fever no cough. 1 gram daily."
    assert finish("No fever, um, no cough. 1 gram daily.") == "No fever no cough. 1 g daily."


@pytest.mark.parametrize("raw, want", [
    ("I started prednisone 20 mg, sorry, 15 mg daily.", "I started prednisone 15 mg daily."),
    ("I started prednisone 20 mg. Sorry, 15 mg daily.", "I started prednisone 15 mg daily."),
    ("prednisone 20 mg, sorry, 15 daily", "prednisone 15 mg daily"),     # the unit said once carries over
    ("a disc protrusion at L4-5, sorry, L5-S1, touching", "a disc protrusion at L5-S1, touching"),
    ("pain in the left, I mean, right knee", "pain in the right knee"),
    ("BP 138/78, sorry, 140/80 today.", "BP 140/80 today."),
    ("Review on Tuesday, sorry, Wednesday.", "Review on Wednesday."),
])
def test_self_corrections_keep_what_was_meant(raw, want):
    from text_fixes import apply_self_corrections
    assert apply_self_corrections(raw) == want


@pytest.mark.parametrize("text", [
    "I'm sorry to hear about 5, sorry I was late.",
    "He is upset, sorry, and tearful.",
    "She says sorry, 2 times a day, to her husband.",     # different kinds: a word, then a number
])
def test_ordinary_sorry_is_left_alone(text):
    from text_fixes import apply_self_corrections
    assert apply_self_corrections(text) == text


@pytest.mark.parametrize("raw, want", [
    ("Her T-score is minus 3.1 at the hip.", "Her T-score is -3.1 at the hip."),
    ("5 minus 3 is 2, plus or minus 2 mmHg.", "5 minus 3 is 2, plus or minus 2 mmHg."),
    ("ceftriaxone 1 gram IV, then 2 grams", "ceftriaxone 1 g IV, then 2 g"),
    ("FEV1 2.1 liters, 1.5 litres a day, 70 kilograms, 500 milligrams", "FEV1 2.1 L, 1.5 L a day, 70 kg, 500 mg"),
    ("10 units of insulin", "10 units of insulin"),                      # never "U"
    ("a gram of prevention", "a gram of prevention"),                    # only after a number
])
def test_signs_and_units_as_written(raw, want):
    from text_fixes import write_signs_and_units
    assert write_signs_and_units(raw) == want
