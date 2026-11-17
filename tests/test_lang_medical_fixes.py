"""Fixes found on real and synthetic medical speech in Spanish and French."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import lang_commands  # noqa: E402
import lang_packs  # noqa: E402

ES = lang_packs.get("es")
FR = lang_packs.get("fr")


def final(text, pack):
    return lang_commands.apply(lang_commands.format_readings(text, pack), pack, punctuation=False)


@pytest.mark.parametrize("raw, want", [
    ("Tome sólo un comprimido.", "Tome solo un comprimido."),
    ("Vamos a tomarle la atención. Tiene 150-95.", "Vamos a tomarle la tensión. Tiene 150/95."),
    ("La atención arterial es normal.", "La tensión arterial es normal."),
    ("Te hicieron un tag de tórax.", "Te hicieron un TAC de tórax."),
    ("Amoxicilina-clavulánico 875-125 cada 8 horas.", "Amoxicilina-clavulánico 875/125 cada 8 horas."),
    ("Frecuencia de 72 latidos por minuto.", "Frecuencia de 72 lpm."),
])
def test_spanish_fixes(raw, want):
    assert final(raw, ES) == want


@pytest.mark.parametrize("text", [
    "Gracias por la atención.",
    "Consulte con su médico de atención primaria.",
    "Mejora la memoria y la atención.",
    "Entre 10-15 minutos, de 4-6 semanas.",
    "Llame al 555-123-456.",
])
def test_spanish_left_alone(text):
    assert final(text, ES) == text
