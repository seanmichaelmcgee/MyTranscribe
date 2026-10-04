"""Score local trial JSON without importing either inference runtime.

Uses the historical name-insensitive metrics. Raw output is compared to spoken
references; cleaned output to written references. Never prints transcript text.
Numbers/negation mismatches and formatting counts are review signals, not proof
of clinical correctness. No denominators or partial runs are silently omitted.
"""
import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from asr_trial_common import ROOT, load_corpus, local_result_path, source_hashes, write_json
sys.path.insert(0, str(ROOT / "src"))
from eval_metrics import Breakdown, breakdown, load_medical_words, normalize_words, term_hits
from vocab import DEFAULT_LEXICON_FILES, CORRECTION_ONLY_FILES
from wordfreq import zipf_frequency

# Same fallback names as make_snippets.NAMES; do not import its audio generator.
NAMES = {27: ["Okafor", "Lena", "Brooks"], 28: ["Haddad", "Victor", "Nguyen"],
         29: ["Chen", "Alice", "Moreau"]}


def entry_names(e):
    if e.get("names"):
        return e["names"]
    try:
        return NAMES.get(int(e.get("scenario", "x_")[:2]), [])
    except ValueError:
        return []


def distribution(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return dict(n=0, mean=None, p50=None, p95=None, maximum=None)
    # Nearest-rank p95; no extrapolation from tiny samples.
    import math
    return dict(n=len(values), mean=statistics.mean(values), p50=statistics.median(values),
                p95=values[max(0, math.ceil(.95 * len(values))-1)], maximum=values[-1])


def format_counts(reference, hypothesis):
    return (reference.count("\n") == hypothesis.count("\n") and
            reference.count('"') == hypothesis.count('"'))


def number_items(text):
    return re.findall(r"(?m)^\s*(\d{1,2})\.\s", text)


def risk_tokens(text):
    words = normalize_words(text)
    numbers = [w for w in words if any(c.isdigit() for c in w)]
    negations = [w for w in words if w in {"no", "not", "without", "denies", "denied", "negative"}]
    return numbers, negations


def validate_run(run, entries, corpus_hash):
    if run.get("schema") != 1 or run.get("completed") is not True:
        raise ValueError("Refusing an incomplete or unsupported run")
    if run.get("corpus_sha256") != corpus_hash:
        raise ValueError("Corpus audio/reference metadata changed; rerun before comparing")
    if run.get("source_sha256") != source_hashes():
        raise ValueError("Scoring/pipeline source changed since this run")
    if run.get("versions", {}).get("wordfreq") != "3.1.1":
        raise ValueError("Word-frequency scorer version mismatch")
    repeats = run.get("repeats")
    if not isinstance(repeats, int) or repeats < 1:
        raise ValueError("Invalid repeat count")
    expected = {(e["clip_id"], repeat): e for e in entries for repeat in range(repeats)}
    actual = {}
    for item in run["utterances"]:
        key = (item["clip_id"], item["repeat"])
        if key in actual or key not in expected:
            raise ValueError("Duplicate or unexpected clip/repeat")
        if item["audio_sha256"] != expected[key]["audio_sha256"]:
            raise ValueError("Audio fingerprint mismatch")
        if any(not isinstance(item.get(field), str) for field in ("raw", "cleaned")):
            raise ValueError("Missing transcript variants")
        actual[key] = item
    if set(actual) != set(expected):
        raise ValueError("Missing clips; refusing partial scorecard")


def score_run(run, entries):
    zipf = lambda w: zipf_frequency(w, "en")
    medical = load_medical_words(list(DEFAULT_LEXICON_FILES) + list(CORRECTION_ONLY_FILES), zipf=zipf)
    by_id = {e["clip_id"]: e for e in entries}
    result = {}
    for variant in ("raw", "cleaned"):
        totals = defaultdict(Breakdown)
        terms, fmt, numbered, signals, timing = (defaultdict(list) for _ in range(5))
        per_clip = []
        for item in run["utterances"]:
            e = by_id[item["clip_id"]]
            ref = e.get("spoken", e["reference"]) if variant == "raw" else e["reference"]
            hyp = item[variant]
            term_words = {w for term in e.get("terms", []) for w in normalize_words(term) if zipf(w) < 4.0}
            b = breakdown(ref, hyp, names=entry_names(e), is_medical=lambda w: w in medical or w in term_words, zipf=zipf)
            found, missed = term_hits(e.get("terms", []), hyp)
            format_ok = format_counts(ref, hyp)
            number_ok = number_items(ref) == number_items(hyp)
            numbers_ref, neg_ref = risk_tokens(ref)
            numbers_hyp, neg_hyp = risk_tokens(hyp)
            review = dict(numeric_mismatch=numbers_ref != numbers_hyp, negation_mismatch=neg_ref != neg_hyp)
            categories = (e.get("category") or e.get("profile") or "all", "ALL")
            for cat in set(categories):
                totals[cat].add(b)
                terms[cat].append((len(found), len(found)+len(missed)))
                fmt[cat].append(format_ok)
                numbered[cat].append(number_ok)
                signals[cat].append(review)
                timing[cat].append(item)
            per_clip.append(dict(clip_id=item["clip_id"], repeat=item["repeat"], **b.rates(),
                                 counts={k:getattr(b,k) for k in ("words","errors","medical","medical_errors","common","common_errors")},
                                 missed_terms=missed, rare_unmatched=b.invented,
                                 medical_missed=b.medical_missed, format_counts_ok=format_ok,
                                 numbering_ok=number_ok, **review))
        summary = {}
        for cat, b in totals.items():
            hits = sum(x[0] for x in terms[cat]); total = sum(x[1] for x in terms[cat])
            summary[cat] = dict(**b.rates(), counts={k:getattr(b,k) for k in ("words","errors","medical","medical_errors","common","common_errors")},
                                terms=round(100*hits/total,1) if total else None,
                                term_counts=[hits,total], format=f"{sum(fmt[cat])}/{len(fmt[cat])}",
                                numbering=f"{sum(numbered[cat])}/{len(numbered[cat])}",
                                review_signals={k:sum(s[k] for s in signals[cat]) for k in ("numeric_mismatch","negation_mismatch")},
                                processing_s=distribution([i.get("processing_s") for i in timing[cat]]),
                                stop_to_text_s=distribution([i.get("stop_to_text_s") for i in timing[cat]]),
                                rtf=distribution([i.get("rtf") for i in timing[cat]]),
                                peak_allocated_vram_mb=distribution([i.get("peak_allocated_vram_mb") for i in timing[cat]]))
        result[variant] = dict(reference="spoken" if variant == "raw" else "written", summary=summary, utterances=per_clip)
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", action="append", required=True, type=Path)
    ap.add_argument("--run", action="append", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only")
    args = ap.parse_args(argv)
    out = local_result_path(args.out)
    entries, corpus_hash = load_corpus(args.manifest, args.only)
    scored = {}
    for path in args.run:
        run = json.loads(path.read_text(encoding="utf-8"))
        validate_run(run, entries, corpus_hash)
        label = path.stem
        if label in scored:
            raise ValueError("Run filenames must have unique stems")
        scores = score_run(run, entries)
        scored[label] = dict(engine=run["engine"], config=run["config"], replay=run["replay"],
                             load_s=run["load_s"], warmup_s=run["warmup_s"], scores=scores)
        print(f"\n{label}: {run['engine']} ({run['replay']})")
        for variant in ("raw", "cleaned"):
            print(f"{variant}: category WER medical common rare/100 terms format numbering")
            for cat,s in sorted(scores[variant]["summary"].items()):
                print(f"{cat}: {s['wer']:.1f} {s['medical_wer']:.1f} {s['common_wer']:.1f} "
                      f"{s['invented_per_100']:.1f} {s['terms']} {s['format']} {s['numbering']}")
    write_json(out, dict(schema=1, corpus_sha256=corpus_hash, source_sha256=source_hashes(), runs=scored))
    return 0


if __name__ == "__main__":
    sys.exit(main())
