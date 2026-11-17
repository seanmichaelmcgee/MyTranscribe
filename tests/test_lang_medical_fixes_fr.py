"""Fixes found on French medical dictations (development part) and a subtitle-line bug."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import lang_commands  # noqa: E402
import lang_packs  # noqa: E402

FR = lang_packs.get("fr")
ES = lang_packs.get("es")


def final(text, pack=FR):
    return lang_commands.apply(lang_commands.format_readings(text, pack), pack, punctuation=False)


@pytest.mark.parametrize("raw, want", [
    ("Tension artérielle à 128 sur 78 mg.", "Tension artérielle à 128/78 mmHg."),
    ("Pression à 165-80 mhg.", "Pression à 165/80 mmHg."),
    ("PaO2 à 68 millimètres de mercure.", "PaO2 à 68 mmHg."),
    ("Créatininémie à 143 micromoles par litre.", "Créatininémie à 143 µmol/L."),
    ("Créatininémie à 150 µmol par litre.", "Créatininémie à 150 µmol/L."),
    ("Cholestérol total à 2,3 gl et CRP à 45 mgl.", "Cholestérol total à 2,3 g/L et CRP à 45 mg/L."),
    ("Oxygène à 2 litres par minute.", "Oxygène à 2 L/min."),
])
def test_french_units(raw, want):
    assert final(raw) == want


@pytest.mark.parametrize("text", [
    "Suivi dans 10-15 jours.",
    "Paracétamol 1 g, 3 fois par jour.",
    "Il prend 5 mg par jour.",
])
def test_french_left_alone(text):
    assert final(text) == text


def test_subtitle_line_in_the_middle_keeps_the_rest():
    text = "Bilan normal. Sous-titrage ST' 501. Une VS à 45 mm. Cordialement."
    assert lang_commands.clean(text, FR) == "Bilan normal. Une VS à 45 mm. Cordialement."


def test_subtitle_line_at_the_end_still_goes():
    assert lang_commands.clean("Cordialement. Sous-titrage Société Radio-Canada", FR) == "Cordialement."
    assert lang_commands.clean("Hasta luego. Subtítulos realizados por la comunidad de Amara.org", ES) == "Hasta luego."


def test_prompts_fit_the_model(monkeypatch):
    # About 3 characters per token in French; the model keeps 223 prompt tokens.
    assert len(lang_commands.prompt_for(FR, True)) < 223 * 3.4
