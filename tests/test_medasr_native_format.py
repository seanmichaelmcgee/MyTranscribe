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


@pytest.mark.parametrize('boundary', ['{newline}', '{new paragraph}', '\n', '\n\n',
                                      'New line.', 'Next line,', 'New paragraph.'])
@pytest.mark.parametrize('item', ['One {period}', 'NUMBER one {period}',
                                 'Number one period', 'one period.', '1 full stop,'])
def test_mixed_layout_is_resolved_before_item_numbering(boundary, item):
    text = f'Plan. {boundary} {item} No pain; continue 0.5 mg.'
    br = '\n\n' if 'paragraph' in boundary.lower() or boundary == '\n\n' else '\n'
    expected = f'Plan.{br}1. No pain; continue 0.5 mg.'
    assert render_native(text) == expected
    assert finish(text) == expected


def test_multiple_mixed_items_and_commands_in_one_pass():
    text = ('Plan. New line. One {period} No fever.'
            ' {newline} Number two period Review 2.5 mg.'
            ' Next line. Three {period} Do not stop.'
            ' {new paragraph} Monitor.')
    expected = 'Plan.\n1. No fever.\n2. Review 2.5 mg.\n3. Do not stop.\n\nMonitor.'
    assert render_native(text) == expected
    assert render_native(expected) == expected


@pytest.mark.parametrize('text', [
    'No new line of therapy and no new paragraph in the note.',
    'New line of therapy is not needed.',
    'New paragraph in the note is incomplete.',
    'One period of pain, two cycles, no bleeding.',
    'one period of nausea\n2 periods of pain\n2.5 mg daily\n120/80 mmHg',
    'No chest pain, negative swab, no fever; 0.5 mg, eGFR 45, type two diabetes.',
    'Follow the next line of the protocol.',
    'number two tablets daily; number 12 is unchanged.',
])
def test_adapter_leaves_ordinary_layout_words_numbers_and_negation(text):
    assert render_native(text) == text
    assert postprocess_native(text, None) == text


@pytest.mark.parametrize('marker', [
    '{new line, review}', '{unknown next line. command}',
    '{number two period. review}', '{PERIOD}', '{new line}',
])
def test_mixed_spoken_commands_do_not_interpret_unknown_marker_contents(marker):
    text = f'Plan. New line. One {{period}} Review {marker} {{newline}} Two {{period}} No pain.'
    expected = f'Plan.\n1. Review {marker}\n2. No pain.'
    assert render_native(text) == expected
    assert postprocess_native(text, str.upper) == f'PLAN.\n1. REVIEW {marker}\n2. NO PAIN.'


def test_unknown_uppercase_period_is_not_an_item_command():
    assert render_native('One {PERIOD} No change') == 'One {PERIOD} No change'


def test_damaged_layout_and_item_tokens_remain_visible_for_review():
    assert render_native('Plan. newline} One {period} Review') == 'Plan. newline} One. Review'
    assert render_native('Plan {newline} wo {period} No pain') == 'Plan\nwo. No pain'


def test_only_explicit_item_numbers_change_clinical_words_remain():
    text = 'Plan {newline} Two {period} Type two diabetes; one tablet, no fever, A1c 6.8.'
    assert render_native(text) == 'Plan\n2. Type two diabetes; one tablet, no fever, A1c 6.8.'


def test_multiline_unknown_marker_preserves_internal_commands_and_whitespace():
    marker = '{unknown \n new line.\nnumber two period. review}'
    text = f'Plan {{newline}} {marker} {{newline}} Three {{period}} Review'
    assert render_native(text) == f'Plan\n{marker}\n3. Review'
    assert postprocess_native(text, str.upper) == f'PLAN\n{marker}\n3. REVIEW'


@pytest.mark.parametrize('number', ['0', '20', '99', 'zero', 'TWENTY'])
def test_native_item_range_is_bounded_and_case_insensitive(number):
    expected = {'zero': '0', 'TWENTY': '20'}.get(number, number)
    assert render_native(f'Plan {{newline}} NuMbEr {number} {{period}} Review') == f'Plan\n{expected}. Review'


@pytest.mark.parametrize('number', ['100', 'twenty one', '0.5', '-2', '120/80'])
def test_native_period_does_not_turn_non_item_numbers_into_items(number):
    assert render_native(f'Plan {{newline}} {number} {{period}} Review') == f'Plan\n{number}. Review'


@pytest.mark.parametrize('boundary', ['.', '{period}'])
@pytest.mark.parametrize('command', ['new line', 'next line', 'new paragraph'])
def test_spoken_layout_can_follow_either_native_or_written_punctuation(boundary, command):
    punctuation = '.' if boundary == '.' else ' {period}'
    text = f'Plan{punctuation} {command} Number two {{period}} No fever.'
    br = '\n\n' if command == 'new paragraph' else '\n'
    assert finish(text) == f'Plan.{br}2. No fever.'


def test_unknown_marker_does_not_make_an_unpunctuated_phrase_a_command():
    text = '{unknown} new line review later'
    assert render_native(text) == text
