"""Formatting policy checks; no model access, inference or scoring references."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from medasr_native_format import postprocess_native, render_native
from voice_commands import apply


def finish(text):
    return apply(render_native(text))


def test_explicit_layout_quotes_and_punctuation():
    assert finish('Review {newline} {open quote} follow up {close quote} {period}') == 'Review\n"Follow up".'
    assert finish('Use {open quote} renal {close quote} then review') == 'Use "renal" then review'
    assert finish('Abdomen SNT {new paragraph} Impression {period} Normal') == 'Abdomen SNT\n\nImpression. Normal'


def test_numbering_uses_only_explicit_period_and_line_boundaries():
    assert finish('one {period} Renal normal {newline} number two {period} Review') == '1. Renal normal\n2. Review'
    assert finish('three {period} Three findings') == '3. Three findings'
    assert render_native('one period of pain, two cycles, 2.5 mg, no new line of therapy') == 'one period of pain, two cycles, 2.5 mg, no new line of therapy'
    assert finish('One {period} Normal') == '1. Normal'
    assert finish('About one {period} Review') == 'About one. Review'


@pytest.mark.parametrize('text', ['{unknown drug}', '{new line}', '{next}', '{PERIOD}', '{open quotes}', '{end dictation}'])
def test_unknown_and_unreviewed_marker_spellings_are_preserved(text):
    assert render_native(text) == text
    assert postprocess_native(text, str.upper) == text


def test_unknown_markers_are_protected_from_medical_corrections():
    text = 'renal {unknown medicine} normal {newline} review'
    assert postprocess_native(text, str.upper) == 'RENAL {unknown medicine} NORMAL\nREVIEW'


def test_no_clinical_content_insertion_or_numerical_rewrite():
    assert finish('No chest pain, 0.5 mg, eGFR 45 {period}') == 'No chest pain, 0.5 mg, eGFR 45.'
    assert render_native('') == ''
    assert render_native('plain prose') == 'plain prose'
