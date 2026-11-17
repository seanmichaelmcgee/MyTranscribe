"""Drug names put right where a drug belongs (part of Extra corrections)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

pytest.importorskip("rapidfuzz")
pytest.importorskip("jellyfish")
pytest.importorskip("wordfreq")

import drug_names  # noqa: E402
from text_fixes import format_readings  # noqa: E402


@pytest.mark.parametrize("raw, want", [
    # ordinary words that together sound like the drug, before a dose
    ("Okay to renew Ram and Pearl 5 mg daily for 3 months.", "Okay to renew ramipril 5 mg daily for 3 months."),
    ("Current medications include dorsal amide 2 mg daily.", "Current medications include dorzolamide 2 mg daily."),
    # a leading digit heard for a syllable
    ("He takes budesonide and 4-Motorol twice daily and cetirizine 10 mg as needed.",
     "He takes budesonide and formoterol twice daily and cetirizine 10 mg as needed."),
    # a unit said twice: the correction is what was meant
    ("She takes levothyroxine 75 mg micrograms daily.", "She takes levothyroxine 75 mcg daily."),
    # near misses anywhere
    ("Started osmertinib last month.", "Started osimertinib last month."),
    # looser in a drug position; the "and" before it stays
    ("Home medications are caprigolin 0.5 mg weekly.", "Home medications are cabergoline 0.5 mg weekly."),
    ("She takes amlodipine 10 mg daily and labatol 100 mg twice daily.",
     "She takes amlodipine 10 mg daily and labetalol 100 mg twice daily."),
    ("Lfusacin 10 mg at bedtime was renewed.", "Alfuzosin 10 mg at bedtime was renewed."),
])
def test_drug_names_fixed(raw, want):
    assert drug_names.apply(raw) == want


@pytest.mark.parametrize("text", [
    "He takes ramipril 10 mg daily, metformin 1000 mg twice daily and rosuvastatin 20 mg daily.",
    "Thank you for seeing Mr. Luis Castellano, a 45-year-old man with a changing mole on his upper back.",
    "Thank you for seeing Mrs. Evelyn Marchetti, an 81-year-old woman with 2 falls in the past month.",
    "She takes no regular medications. Her mother has migraine.",
    "Please call and advise the potassium is slightly high at 5.4. Repeat the lab next week.",
    "Hemoglobin is 118, slightly low. Start iron once daily and recheck in 3 months.",
    "He takes tiotropium once daily, apixaban 5 mg twice daily, bisoprolol 5 mg daily and allopurinol 300 mg daily.",
    "The pain is worse on stairs and after sitting. She uses acetaminophen as needed with partial relief.",
    "Oxygen saturation was 93% on room air and respiratory rate was 18.",
    "He drinks 2 beers a day and has never smoked.",
    "Medications include thymol mouthwash twice daily.",          # a real ingredient that is not a target
])
def test_correct_text_is_left_alone(text):
    assert drug_names.apply(text) == text


def test_name_after_title_is_not_a_drug():
    assert drug_names.apply("Dr. Labatol takes over the clinic daily.") == "Dr. Labatol takes over the clinic daily."


def test_list_has_targets_and_protected_names():
    targets, protected = drug_names.load_names()
    assert "ramipril" in targets and "formoterol" in targets
    assert "thymol" in protected and "thymol" not in targets


def test_part_of_extra_corrections():
    assert format_readings("Okay to renew Ram and Pearl five milligrams daily.") == "Okay to renew ramipril 5 mg daily."


def test_missing_list_passes_text_through(tmp_path):
    assert drug_names.load_names(tmp_path / "none.txt") == ([], [])
