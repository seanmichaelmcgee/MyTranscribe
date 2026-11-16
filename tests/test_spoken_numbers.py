"""Number words -> digits and unit abbreviations (part of Extra corrections)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from spoken_numbers import normalise  # noqa: E402
from text_fixes import format_readings  # noqa: E402


@pytest.mark.parametrize("raw, want", [
    ("Hgb is one hundred and twenty four grams per liter.", "Hgb is 124 grams per liter."),
    ("EGFR is fifty eight.", "EGFR is 58."),
    ("potassium is four point two", "potassium is 4.2"),
    ("pain for six weeks, relieved within five minutes", "pain for 6 weeks, relieved within 5 minutes"),
    ("aspirin, 81 milligrams daily, bisoprolol, 2.5 milligrams daily", "aspirin, 81 mg daily, bisoprolol, 2.5 mg daily"),
    ("Hydromorphone one milligram as needed", "Hydromorphone 1 mg as needed"),
    ("metformin five hundred milligrams twice daily", "metformin 500 mg twice daily"),
    ("one thousand micrograms", "1000 mcg"),
    ("a forty-six year old woman", "a 46 year old woman"),
    ("thirty pack years", "30 pack years"),
    ("two thousand and five", "2005"),
    ("saturation ninety eight percent", "saturation 98%"),
    ("twenty-five millimetres", "25 mm"),
    ("after two blocks of walking, one flight of stairs, two falls and two beers a day",
     "after 2 blocks of walking, 1 flight of stairs, 2 falls and 2 beers a day"),
])
def test_numbers_and_units(raw, want):
    assert normalise(raw) == want


@pytest.mark.parametrize("text", [
    "No one else was present.",
    "One of the two options was chosen.",
    "She has three children and one brother.",
    "The first of four options.",
    "Seen one time before.",
    "Type two diabetes is well controlled.",
    "Take one or two as needed.",
    "Grade three out of six murmur.",
    "Already 124 g/L and 5 mg.",
    "nine one one was called",
])
def test_ordinary_number_words_stay(text):
    assert normalise(text) == text


def test_readings_include_number_words():
    assert format_readings("Hgb is one hundred and twenty four grams per liter, pressure one thirty eight over "
                           "seventy eight.") == "Hgb is 124 g/L, pressure 138/78."
