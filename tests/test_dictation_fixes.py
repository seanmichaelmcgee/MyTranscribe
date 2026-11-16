"""Dates of birth and chart numbers read out digit by digit (part of Extra corrections)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dictation_fixes import apply  # noqa: E402
from text_fixes import format_readings  # noqa: E402


@pytest.mark.parametrize("raw, want", [
    ("Date of birth 04-2-1-1998. The patient", "Date of birth 04/21/1998. The patient"),
    ("Date of birth 0-8-1-2-19-84. Subjective", "Date of birth 08/12/1984. Subjective"),
    ("Date, of birth 1119, 1988. This is", "Date, of birth 11/19/1988. This is"),
    ("date of birth 09121946.", "date of birth 09/12/1946."),
    ("Chart number 8, 8-0-7-2-9. Date of birth 01251991.", "Chart number 880729. Date of birth 01/25/1991."),
    ("Chart number 114710, 4. Date of birth 1119 1988.", "Chart number 1147104. Date of birth 11/19/1988."),
])
def test_dates_of_birth_and_chart_numbers_are_put_together(raw, want):
    assert apply(raw) == want


@pytest.mark.parametrize("text", [
    "Date of birth March 3, 1984.",
    "Date of birth 1984.",
    "Date of birth 45-67-1990.",                              # not a day and month
    "Chart number pending. 3 days of cough.",
    "Her chart shows 2 visits, 3 calls.",
    "for Quaim Thibodaux. THIBODEAUX. Seen today.",           # a spelled name is left exactly as heard
])
def test_other_text_is_left(text):
    assert apply(text) == text


def test_it_is_part_of_extra_corrections():
    assert format_readings("Chart number 8, 8-0-7-2-9. Date of birth 01251991. BP 138 over 78.") == \
        "Chart number 880729. Date of birth 01/25/1991. BP 138/78."
