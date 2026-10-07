"""Persistent personal curriculum and opt-in equivalence scoring. No ASR or network."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from asr_trial_common import ROOT, canonical_hash, load_corpus, local_result_path, sha256, write_json

TEMPLATE = ROOT / 'docs' / 'samples' / 'personal_curriculum_v1.json'
DEFAULT_ROOT = ROOT / 'results_1060' / 'personal_curriculum'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def validate_policy(policy):
    """Accept explicit spelling groups only; reject conflicting or numeric rules."""
    if policy.get('schema') != 'personal-curriculum-v1':
        raise ValueError('Unsupported curriculum policy')
    mapping = {}
    canonicals = set()
    for group in policy.get('accepted_spellings', []):
        canonical = group['canonical'].lower()
        if canonical in canonicals or not group.get('authority'):
            raise ValueError('Unique canonical and explicit authority required')
        canonicals.add(canonical)
        accepted = group['accepted']
        if not isinstance(accepted, list) or canonical not in [v.lower() for v in accepted]:
            raise ValueError('Canonical must be an accepted spelling')
        for value in accepted:
            key = value.lower()
            if not re.fullmatch(r'[a-z]+(?:[ -][a-z]+)*', key):
                raise ValueError('Spelling equivalences cannot rewrite numbers, units or markup')
            if key in mapping and mapping[key] != canonical:
                raise ValueError('Conflicting accepted spelling')
            mapping[key] = canonical
    return mapping


def equivalent_text(text, policy):
    """Normalize evaluation copies only, with complete-token boundaries."""
    mapping = validate_policy(policy)
    if not mapping:
        return text
    pattern = re.compile(r'(?<!\w)(?:' + '|'.join(re.escape(k) for k in
                         sorted(mapping, key=len, reverse=True)) + r')(?!\w)', re.I)
    return pattern.sub(lambda match: mapping[match.group().lower()], text)


def initialize(folder=DEFAULT_ROOT):
    """Seed once; reopening never discards personal feedback or edits."""
    folder = local_result_path(Path(folder))
    folder.mkdir(parents=True, exist_ok=True)
    policy_path = folder / 'curriculum.json'
    if not policy_path.exists():
        policy = json.loads(TEMPLATE.read_text(encoding='utf-8'))
        validate_policy(policy)
        write_json(policy_path, policy)
        append_event(folder, dict(kind='initialized', template_sha256=sha256(TEMPLATE)))
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    validate_policy(policy)
    return folder, policy


def append_event(folder, event):
    """Append explicit human feedback; preserve the existing record."""
    with (Path(folder) / 'feedback.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(timestamp_utc=stamp(), **event), ensure_ascii=False) + '\n')


def export_candidate(folder, policy):
    """Make a compatible lexicon artifact; never activate an app override."""
    target = Path(folder) / 'candidates' / ('vocabulary_v' + str(policy['version']) + '.txt')
    lines = ['# Candidate personal vocabulary; requires paired trials before activation.']
    grouped = {}
    for row in policy['seed_terms']:
        if row['category'] not in ('drug', 'dx', 'lab', 'test', 'abbr', 'other'):
            raise ValueError('Unknown vocabulary category')
        if not re.fullmatch(r'[a-z][a-z_-]*', row['topic']):
            raise ValueError('Invalid topic')
        if any(c in row['term'] for c in '\r\n,:|'):
            raise ValueError('Term would change vocabulary structure')
        grouped.setdefault(row['topic'], {}).setdefault(row['category'], []).append(row['term'])
    for topic, categories in grouped.items():
        lines.append('## personal_' + topic + ' | ' + ', '.join(
            term for values in categories.values() for term in values))
        for category, terms in categories.items():
            lines.append(category + ': ' + ', '.join(terms))
    text = '\n'.join(lines) + '\n'
    if target.exists() and target.read_text(encoding='utf-8') != text:
        raise ValueError('Candidate version already exists; increment policy version')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')
    return target


def evaluate(run, entries, policy):
    """Retain literal metrics beside accepted-spelling metrics on frozen run scope."""
    from score_asr_trial import score_run, validate_run
    identifiers = {item['clip_id'] for item in run['utterances']}
    selected = [entry for entry in entries if entry['clip_id'] in identifiers]
    if {entry['clip_id'] for entry in selected} != identifiers:
        raise ValueError('Run contains audio outside supplied manifests')
    corpus = canonical_hash([{k: v for k, v in e.items() if k != '_path'} for e in selected])
    validate_run(run, selected, corpus)
    legacy = score_run(run, selected)
    accepted_run, accepted_entries = deepcopy(run), deepcopy(selected)
    for entry in accepted_entries:
        for key in ('spoken', 'reference'):
            if key in entry:
                entry[key] = equivalent_text(entry[key], policy)
        entry['terms'] = list(dict.fromkeys(equivalent_text(t, policy) for t in entry.get('terms', [])))
    for item in accepted_run['utterances']:
        for key in ('raw', 'cleaned'):
            item[key] = equivalent_text(item[key], policy)
    return dict(selected_clip_ids=sorted(identifiers), original_corpus_sha256=corpus,
                literal=legacy, accepted_spellings=score_run(accepted_run, accepted_entries))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init')
    commands.add_parser('status')
    commands.add_parser('export-candidate')
    feedback = commands.add_parser('feedback')
    feedback.add_argument('--note', required=True)
    feedback.add_argument('--kind', choices=['term', 'medication', 'style', 'accepted-spelling', 'capture'], required=True)
    score = commands.add_parser('evaluate')
    score.add_argument('--manifest', action='append', type=Path, required=True)
    score.add_argument('--run', action='append', type=Path, required=True)
    score.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    folder, policy = initialize(args.root)
    if args.command == 'feedback':
        append_event(folder, dict(kind=args.kind, note=args.note, authority='Explicit operator-recorded human feedback',
                                 promotion='review_required; policy/app unchanged'))
        print('Feedback retained for review')
    elif args.command == 'export-candidate':
        print(export_candidate(folder, policy))
    elif args.command == 'evaluate':
        out = local_result_path(args.out)
        if out.exists():
            raise ValueError('Preserve earlier policy scores; choose a new output')
        entries, _ = load_corpus(args.manifest)
        result = dict(schema='personal-curriculum-score-v1', policy_sha256=sha256(folder/'curriculum.json'),
                      scorer_sha256=sha256(Path(__file__)), policy_version=policy['version'],
                      accepted_spellings=policy['accepted_spellings'], runs={})
        for path in args.run:
            key = str(path.resolve())
            if key in result['runs']:
                raise ValueError('Duplicate run')
            run = json.loads(path.read_text(encoding='utf-8'))
            result['runs'][key] = dict(output_sha256=sha256(path), scores=evaluate(run, entries, policy))
        write_json(out, result)
        print(json.dumps(dict(policy_version=policy['version'], runs=len(result['runs']), out=str(out))))
    else:
        print(json.dumps(dict(root=str(folder), version=policy['version'], primary_capture=policy['primary_capture'],
                             accepted_spellings=policy['accepted_spellings'],
                             adaptation_status=policy['adaptation_status']), indent=2))


if __name__ == '__main__':
    main()
