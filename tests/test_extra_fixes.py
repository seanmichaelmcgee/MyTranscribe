"""Extra corrections (Options, off by default): readings format and same-sound term correction."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from text_fixes import format_readings  # noqa: E402
from vocab_correct import make_corrector  # noqa: E402


@pytest.mark.parametrize("raw, want", [
    ("Blood pressure today is 138 over 78, measured seated.", "Blood pressure today is 138/78, measured seated."),
    ("HgB is 124 g per litre.", "HgB is 124 g/L."),
    ("Hemoglobin is 124 grams per liter and potassium 4.2 mmol per litre.",
     "Hemoglobin is 124 g/L and potassium 4.2 mmol/L."),
    ("Glucose 98 mg per decilitre.", "Glucose 98 mg/dL."),
    ("Temperature 37.2 degrees Celsius.", "Temperature 37.2 °C."),
    ("Temp 98.6 degrees Fahrenheit, then 101 degrees F.", "Temp 98.6 °F, then 101 °F."),
    ("Infuse at 5 mg per hour.", "Infuse at 5 mg/h."),
])
def test_readings_are_written_the_chart_way(raw, want):
    assert format_readings(raw) == want


@pytest.mark.parametrize("text", [
    "He is over 65 and takes 2 over the counter tablets.",
    "Seen 3 times per day for 2 weeks.",
    "Bent to 90 degrees of flexion.",
    "Pain 7 over 10.",
    "It took over 100 days, 120 over the year.",
    "Ratio 1.5 over 2.5.",
    "Already written as 138/78 and 124 g/L.",
])
def test_readings_leave_other_text(text):
    assert format_readings(text) == text


@pytest.fixture(scope="module")
def corrector():
    c = make_corrector(["perindopril", "ramipril", "enalapril", "risperidone", "buspirone", "olmesartan",
                        "losartan", "telmisartan", "hydroxyzine", "hydralazine", "metoprolol"])
    if c is None:
        pytest.skip("rapidfuzz / jellyfish / wordfreq not installed")
    return c


def test_same_sound_band_is_opt_in(corrector):
    corrector.same_sound = False
    assert corrector("Prendipril 4 mg and respiradone") == "Prendipril 4 mg and respiradone"
    corrector.same_sound = True
    assert corrector("Prendipril 4 mg and respiradone") == "Perindopril 4 mg and risperidone"
    assert corrector("remapril 5 mg") == "ramipril 5 mg"
    corrector.same_sound = False


def test_same_sound_band_leaves_ambiguous_and_real_words(corrector):
    corrector.same_sound = True
    try:
        # could be olmesartan or telmisartan: neither has the same sound
        assert corrector("tomasartan 40 mg") == "tomasartan 40 mg"
        assert corrector("hydroxyzine, not hydralazine") == "hydroxyzine, not hydralazine"
        assert corrector("the patient remains stable") == "the patient remains stable"
    finally:
        corrector.same_sound = False
