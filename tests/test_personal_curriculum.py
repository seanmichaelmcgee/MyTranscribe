"""Accepted-spelling scoring and persistence; no microphone/model or network."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import personal_curriculum as curriculum


@pytest.fixture
def policy():
    return json.loads(curriculum.TEMPLATE.read_text(encoding='utf-8'))


def test_accepted_variant_is_equivalent_but_malformed_words_stay_visible(policy):
    text = 'Dysdiadokinesia, dysdiadochokinesia, dysdiatokinesia and dysthytokinesia.'
    assert curriculum.equivalent_text(text, policy) == (
        'dysdiadochokinesia, dysdiadochokinesia, dysdiatokinesia and dysthytokinesia.')
    assert curriculum.equivalent_text('predysdiadokinesia dysdiadokinesias', policy) == (
        'predysdiadokinesia dysdiadokinesias')


def test_medication_numbers_negation_and_style_are_unchanged(policy):
    text = 'No nystagmus. Ramipril 5 mg daily, atorvastatin 20 mg nightly. BP 132/78.\n\nPlan.'
    assert curriculum.equivalent_text(text, policy) == text


def test_conflicting_groups_and_numeric_rules_are_rejected(policy):
    conflicting = deepcopy(policy)
    conflicting['accepted_spellings'].append(dict(canonical='other', accepted=['other', 'dysdiadokinesia'], authority='fixture'))
    with pytest.raises(ValueError, match='Conflicting'):
        curriculum.validate_policy(conflicting)
    numeric = deepcopy(policy)
    numeric['accepted_spellings'][0]['accepted'].append('132')
    with pytest.raises(ValueError, match='numbers'):
        curriculum.validate_policy(numeric)


def test_reopening_preserves_feedback_and_personal_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(curriculum, 'local_result_path', lambda p: p)
    folder, first = curriculum.initialize(tmp_path)
    first['style_preferences'] = ['Separate impression and plan']
    curriculum.write_json(folder/'curriculum.json', first)
    curriculum.append_event(folder, dict(kind='style', note='fixture'))
    before = (folder/'feedback.jsonl').read_bytes()
    _, reopened = curriculum.initialize(tmp_path)
    assert reopened['style_preferences'] == first['style_preferences']
    assert (folder/'feedback.jsonl').read_bytes() == before


def test_candidate_export_is_versioned_and_requires_new_version_for_changes(tmp_path, policy):
    path = curriculum.export_candidate(tmp_path, policy)
    from vocab import parse_lexicon_text
    terms = {t.text for t in parse_lexicon_text(path.read_text()).all_terms()}
    assert {'ramipril', 'dysdiadokinesia', 'dysdiadochokinesia'} <= terms
    policy['seed_terms'].append(dict(term='metformin', category='drug', topic='medications'))
    with pytest.raises(ValueError, match='increment'):
        curriculum.export_candidate(tmp_path, policy)
    policy['version'] = 2
    assert curriculum.export_candidate(tmp_path, policy) != path


def test_scoring_keeps_literal_counts_and_inputs_while_crediting_accepted_variant(policy):
    from asr_trial_common import source_hashes, canonical_hash
    entry = dict(clip_id='fixture.wav', audio='fixture.wav', audio_sha256='fixture-hash',
                 scenario='fixture', category='exam', names=[], terms=['dysdiadochokinesia'],
                 spoken='Dysdiadochokinesia.', reference='Dysdiadochokinesia.')
    run = dict(schema=1, completed=True, source_sha256=source_hashes(),
               corpus_sha256=canonical_hash([entry]), versions={'wordfreq': '3.1.1'}, repeats=1,
               utterances=[dict(clip_id='fixture.wav', repeat=0, audio_sha256='fixture-hash',
                                raw='Dysdiadokinesia.', cleaned='Dysdiadokinesia.')])
    before = deepcopy(run)
    result = curriculum.evaluate(run, [entry], policy)
    assert result['literal']['cleaned']['summary']['ALL']['counts']['errors'] == 1
    assert result['accepted_spellings']['cleaned']['summary']['ALL']['counts']['errors'] == 0
    assert result['accepted_spellings']['cleaned']['summary']['ALL']['term_counts'] == [1, 1]
    assert run == before and entry['reference'] == 'Dysdiadochokinesia.'
