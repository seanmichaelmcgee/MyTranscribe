"""Opt-in, offline, bounded Whisper ablations; no recognition happens during plan/compare.

Use plan after source freeze, run ONE variant per invocation with --execute, then
compare all planned variants. Sensitive artifacts must live in ignored results_*.
This has its own schema/validator; do not relabel its records as trial_asr schema 1.
"""
import argparse
import copy
import importlib.metadata
import inspect
import json
import logging
import math
import os
import platform
import subprocess
import sys
import time
import wave
from pathlib import Path

from asr_trial_common import (ROOT, SR, canonical_hash, load_corpus, local_result_path,
                              sha256, source_hashes, source_revision, write_json)

sys.path.insert(0, str(ROOT / "src"))
SCHEMA = "whisper-accuracy-ablation-v1"
PACKAGES = ("numpy", "faster-whisper", "ctranslate2", "wordfreq", "rapidfuzz", "jellyfish")
BASE = dict(prompt="topics", corrector=True, fixes=True, beam=5, patience=2.0, chunk_s=20.0, state="per-clip")
OVERRIDES = {
    "baseline": {},
    "no-topics": dict(prompt="style-tail"),
    "no-corrector": dict(corrector=False),
    "no-fixes": dict(fixes=False),
    "no-post": dict(corrector=False, fixes=False),
    "bare": dict(prompt="none", corrector=False, fixes=False),
    "no-prompt": dict(prompt="none"),
    "style-only": dict(prompt="style-only"),
    "greedy": dict(beam=1, patience=1.0),
    "beam-patience1": dict(patience=1.0),
    "chunk30": dict(chunk_s=30.0),
    "shared-topics": dict(state="shared"),
}
DEFAULT_VARIANTS = "baseline,no-topics,no-corrector,no-fixes,no-prompt,greedy,beam-patience1"


def variant_config(name):
    if name not in OVERRIDES:
        raise ValueError("Unknown variant")
    return dict(BASE, **OVERRIDES[name])


def experiment_sources():
    """Additional fingerprints remain mandatory even if common's list changes."""
    paths = [Path(__file__), ROOT / "src" / "eval_metrics.py",
             ROOT / "scripts" / "score_asr_trial.py", ROOT / "scripts" / "trial_asr.py"]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in paths}


def runtime_versions():
    versions = dict(python=platform.python_version(), platform=platform.platform())
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def model_integrity(path):
    """Require an existing CTranslate2 directory; hash all files, never download."""
    path = Path(path).resolve()
    for name in ("model.bin", "config.json", "tokenizer.json"):
        if not (path / name).is_file():
            raise ValueError("Existing local CTranslate2 model directory required")
    files = {}
    for p in sorted(path.rglob("*")):
        if p.is_file():
            files[p.relative_to(path).as_posix()] = sha256(p)
    return dict(path=str(path), sha256=files)


def fingerprint(value, field):
    return canonical_hash({k: v for k, v in value.items() if k != field})


def check_bounds(entries, variants, repeats, max_clips, max_audio_s, timeout_s):
    if (type(repeats) is not int or not 1 <= repeats <= 3 or
            type(max_clips) is not int or not 1 <= max_clips <= 500 or
            not math.isfinite(max_audio_s) or not 0 < max_audio_s <= 7200 or
            type(timeout_s) is not int or not 1 <= timeout_s <= 7200):
        raise ValueError("Invalid experiment bounds (3 repeats, 500 clips, 7200 s ceilings)")
    if not variants or len(variants) != len(set(variants)) or "baseline" not in variants:
        raise ValueError("Unique variants including baseline required")
    for name in variants:
        variant_config(name)
    if len(entries) > max_clips or sum(e["duration_s"] for e in entries) * repeats > max_audio_s:
        raise ValueError("Corpus exceeds bounds; explicitly select a smaller corpus or raise limits")


def protected_corpus(manifests, only):
    # Enforce both manifests and waveform locations; no copying to tracked paths.
    manifests = [local_result_path(Path(p)) for p in manifests]
    entries, digest = load_corpus(manifests, only)
    for e in entries:
        local_result_path(e["_path"])
    return entries, digest


def make_plan(args):
    out = local_result_path(args.out)
    if out.exists():
        raise ValueError("Refusing to overwrite an existing plan")
    entries, digest = protected_corpus(args.manifest, args.only)
    variants = args.variants.split(",")
    check_bounds(entries, variants, args.repeats, args.max_clips, args.max_audio_s, args.timeout_s)
    plan = dict(schema=SCHEMA, kind="plan", corpus_sha256=digest,
                manifests=[str(p.resolve()) for p in args.manifest], only=args.only,
                source_revision=source_revision(), source_sha256=source_hashes(),
                experiment_sha256=experiment_sources(), versions=runtime_versions(),
                model=model_integrity(args.model_path), device=args.device, compute=args.compute,
                cpu_threads=args.cpu_threads, repeats=args.repeats,
                bounds=dict(max_clips=args.max_clips, max_audio_s=args.max_audio_s, timeout_s=args.timeout_s),
                variants={n: variant_config(n) for n in variants},
                pipeline=dict(environment="bundled only; env/user overrides excluded",
                              context="postprocessed chunks before voice commands",
                              reset="fresh pipeline per clip/repeat except shared-topics reuses it in manifest/repeat order",
                              pcm="trial_asr int16 -> float32 /32768 -> int16 *32767",
                              phantom_filter=True, voice_commands=True, replay="offline",
                              sample_rate=SR, cut_search_s=5.0, cut_frame_ms=30,
                              silence_rms=80, language="en", condition_on_previous_text=False,
                              vad_filter=True, vad_parameters=dict(min_silence_duration_ms=700, speech_pad_ms=300),
                              without_timestamps=True, temperature="installed faster-whisper defaults",
                              token_cap="production FasterWhisperEngine.max_new_tokens"))
    plan["plan_sha256"] = fingerprint(plan, "plan_sha256")
    write_json(out, plan)
    print(f"Plan saved: {len(entries)} clips, {len(variants)} variants; no inference performed")
    return plan


def validate_plan(plan):
    if plan.get("schema") != SCHEMA or plan.get("kind") != "plan":
        raise ValueError("Unsupported plan")
    if plan.get("plan_sha256") != fingerprint(plan, "plan_sha256"):
        raise ValueError("Plan fingerprint mismatch")
    if plan.get("source_sha256") != source_hashes() or plan.get("experiment_sha256") != experiment_sources():
        raise ValueError("Source changed since freeze; make a new plan and rerun ALL variants")
    if plan.get("versions") != runtime_versions():
        raise ValueError("Runtime/dependency versions changed")
    if plan.get("model") != model_integrity(plan["model"]["path"]):
        raise ValueError("Model files changed")
    entries, digest = protected_corpus(plan["manifests"], plan["only"])
    if digest != plan["corpus_sha256"]:
        raise ValueError("Corpus audio/reference/name/category metadata changed")
    check_bounds(entries, list(plan["variants"]), plan["repeats"], **plan["bounds"])
    if any(c != variant_config(n) for n, c in plan["variants"].items()):
        raise ValueError("Variant settings differ from supported controls")
    if plan["device"] not in ("cuda", "cpu") or not 1 <= plan["cpu_threads"] <= 64:
        raise ValueError("Invalid runtime configuration")
    return entries


def audio_inputs(entries):
    """Recognition receives only waveform location/identity, never reference/terms/names."""
    keys = ("clip_id", "audio", "audio_sha256", "duration_s", "_path")
    return [{k: e[k] for k in keys} for e in entries]


def make_pipeline(style, count, cfg, factory=None):
    from text_fixes import BUNDLED_CORRECTIONS
    from vocab import Lexicon, build_text_pipeline
    builder, post = (factory or build_text_pipeline)(
        style, count=count, env={}, correction_files=[BUNDLED_CORRECTIONS])
    if builder is None or post is None:
        raise ValueError("Bundled pipeline unavailable")
    if cfg["corrector"] and post.corrector is None:
        raise ValueError("Corrector dependency unavailable; refusing a mislabeled variant")
    if cfg["fixes"] and post.fixes is None:
        raise ValueError("Text fixes unavailable")
    if cfg["prompt"] == "style-tail":
        # Same PromptBuilder's 160-char tail, budgeting, and trimming, without terms.
        # The production VOCAB=off fallback has a DIFFERENT 200-char tail.
        builder.lexicon = Lexicon()
        builder.default_topics = []
    elif cfg["prompt"] == "none":
        builder = lambda context: ""
    elif cfg["prompt"] == "style-only":
        builder = lambda context: style
    if not cfg["corrector"]:
        post.corrector = None
    if not cfg["fixes"]:
        post.fixes = None
    return builder, post


class DecoderProxy:
    """Override ONLY patience, using production transcribe for all other kwargs."""
    def __init__(self, model, patience):
        self.model, self.patience = model, patience
        self.calls = []
        self.defaults = {k: v.default for k, v in inspect.signature(model.transcribe).parameters.items()
                         if v.default is not inspect.Parameter.empty}
        # Fail on unserializable defaults rather than losing decoder provenance.
        self.defaults = json.loads(json.dumps(self.defaults))

    def __getattr__(self, name):
        return getattr(self.model, name)

    def transcribe(self, audio, **kwargs):
        kwargs["patience"] = self.patience
        self.calls.append({k: v for k, v in kwargs.items() if k != "initial_prompt"})
        return self.model.transcribe(audio, **kwargs)


class TraceEngine:
    def __init__(self, engine):
        self.engine, self.raw_chunks, self.prompts, self.chunk_compute_s = engine, [], [], []
        self.errors = []

    def transcribe(self, audio, prompt=None):
        self.prompts.append(prompt)
        start = time.perf_counter()
        try:
            text = self.engine.transcribe(audio, prompt)
            if not isinstance(text, str):
                raise ValueError("Non-text engine output")
            self.raw_chunks.append(text)
            self.chunk_compute_s.append(time.perf_counter() - start)
            return text
        except Exception:
            self.errors.append("decoder")
            raise


def strict_callback(callback, failures, label):
    """Production catches hook failures; retain evidence and refuse the result."""
    def wrapped(text):
        try:
            return callback(text)
        except Exception:
            failures.append(label)
            raise
    return wrapped


def replay_clip(clip, fw, cfg, style, pipeline=None):
    import numpy as np
    from chunked_transcriber import ChunkedTranscriber, ERROR_PREFIX, filter_phantoms
    from trial_asr import ReplayStream
    from voice_commands import apply

    with wave.open(str(clip["_path"]), "rb") as w:
        pcm = w.readframes(w.getnframes())
        if len(pcm) != w.getnframes() * 2:
            raise ValueError("Truncated waveform")
    pcm = (np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0 * 32767).astype("<i2").tobytes()
    stream, trace, failures = ReplayStream(pcm), TraceEngine(fw), []
    builder, post = pipeline if pipeline is not None else make_pipeline(style, fw.count_tokens, cfg)
    t = ChunkedTranscriber(trace, stream_factory=lambda: (stream, None), base_prompt=style,
                           prompt_builder=strict_callback(builder, failures, "prompt"),
                           postprocess=strict_callback(post, failures, "postprocess"),
                           chunk_target_s=cfg["chunk_s"])
    start = time.perf_counter()
    t.start_recording()
    t._capture_thread.join(timeout=30)
    if t._capture_thread.is_alive():
        t.stop_recording()
        raise ValueError("Replay capture timeout")
    t.stop_recording()
    if not t.wait_until_idle(timeout=180):
        raise ValueError("Decoder timeout")
    if failures or trace.errors or t.capture_error or stream.pos != len(pcm) or any(
            ERROR_PREFIX in text for text in t.transcriptions):
        raise ValueError("Incomplete or failed pipeline; refusing to score")
    compute = sum(trace.chunk_compute_s)
    return dict(clip_id=clip["clip_id"], audio=clip["audio"], audio_sha256=clip["audio_sha256"],
                duration_s=clip["duration_s"], raw=" ".join(trace.raw_chunks),
                filtered=" ".join(filter_phantoms(s) for s in trace.raw_chunks if filter_phantoms(s)),
                cleaned=apply(t.text), raw_chunks=trace.raw_chunks, prompts=trace.prompts,
                chunk_compute_s=trace.chunk_compute_s, processing_s=time.perf_counter()-start,
                compute_s=compute, rtf=compute/clip["duration_s"],
                stop_to_text_s=None, peak_allocated_vram_mb=None)


def execute_worker(plan, variant, out):
    entries = audio_inputs(validate_plan(plan))
    if plan["versions"].get("wordfreq") != "3.1.1" or any(
            plan["versions"].get(p) is None for p in PACKAGES):
        raise ValueError("Existing inference/scoring dependencies required; install nothing in this harness")
    os.environ.update(HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1", TRANSFORMERS_OFFLINE="1")
    # Avoid transcript-bearing exception traces from hooks; progress contains counts only.
    logging.disable(logging.CRITICAL)
    from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs
    from hw_profile import EngineConfig
    from prompt_loader import load_prompt

    cfg = plan["variants"][variant]
    record = dict(schema=SCHEMA, kind="run", completed=False, variant=variant,
                  plan_sha256=plan["plan_sha256"], config=cfg, corpus_sha256=plan["corpus_sha256"],
                  source_sha256=plan["source_sha256"], experiment_sha256=plan["experiment_sha256"],
                  versions=plan["versions"], model=plan["model"], repeats=plan["repeats"], utterances=[])
    write_json(out, record)
    register_cuda_dll_dirs()
    from faster_whisper import WhisperModel
    start = time.perf_counter()
    fw = FasterWhisperEngine(EngineConfig(plan["model"]["path"], plan["device"], plan["compute"],
        plan["cpu_threads"], "frozen accuracy ablation"), beam_size=cfg["beam"],
        model_factory=lambda *a, **kw: WhisperModel(*a, local_files_only=True, **kw))
    if (fw.config.device, fw.config.compute_type) != (plan["device"], plan["compute"]):
        raise ValueError("Device/precision fallback; refusing mislabeled results")
    proxy = DecoderProxy(fw.model, cfg["patience"])
    fw.model = proxy
    record.update(load_s=time.perf_counter()-start, decoder_defaults=proxy.defaults,
                  actual_runtime=dict(device=fw.config.device, compute=fw.config.compute_type,
                                      cpu_threads=fw.config.cpu_threads))
    style = load_prompt(env={})
    if not style:
        raise ValueError("Bundled style prompt unavailable")
    shared = make_pipeline(style, fw.count_tokens, cfg) if cfg["state"] == "shared" else None
    # No reference-dependent warmup, no hidden model/precision switches.
    for repeat in range(plan["repeats"]):
        for index, clip in enumerate(entries):
            proxy.calls.clear()
            item = replay_clip(clip, fw, cfg, style, pipeline=shared)
            item.update(repeat=repeat, decoder_calls=copy.deepcopy(proxy.calls))
            record["utterances"].append(item)
            write_json(out, record)
            print(f"{variant}: clip {index+1}/{len(entries)}, repeat {repeat+1}", flush=True)
    # Recheck all frozen inputs before marking complete; mid-run changes invalidate it.
    validate_plan(plan)
    record["completed"] = True
    record["record_sha256"] = fingerprint(record, "record_sha256")
    write_json(out, record)


def run_variant(args):
    plan_path = local_result_path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_plan(plan)
    if args.variant not in plan["variants"]:
        raise ValueError("Variant not selected in frozen plan")
    if not args.execute:
        raise ValueError("Inference is opt-in: supply --execute after source freeze")
    out = local_result_path(args.out)
    if out.exists():
        raise ValueError("Refusing to overwrite run; use a fresh output path")
    if args.worker:
        execute_worker(plan, args.variant, out)
        return
    # One process/model per selected variant; hard wall timeout includes model load,
    # all clips/repeats, and provenance checks. subprocess.run kills/waits on timeout.
    command = [sys.executable, str(Path(__file__).resolve()), "run", "--plan", str(plan_path),
               "--variant", args.variant, "--out", str(out), "--execute", "--worker"]
    try:
        result = subprocess.run(command, cwd=ROOT, timeout=plan["bounds"]["timeout_s"], check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Bounded worker timed out; incomplete output must not be compared") from exc
    if result.returncode:
        raise ValueError("Variant failed; incomplete output must not be compared")


def validate_run(run, plan, entries):
    if run.get("schema") != SCHEMA or run.get("kind") != "run" or run.get("completed") is not True:
        raise ValueError("Incomplete or unsupported run")
    if run.get("record_sha256") != fingerprint(run, "record_sha256"):
        raise ValueError("Run fingerprint mismatch")
    for key in ("plan_sha256", "corpus_sha256", "source_sha256", "experiment_sha256", "versions", "model", "repeats"):
        if run.get(key) != plan[key]:
            raise ValueError("Run provenance mismatch: " + key)
    name = run.get("variant")
    if name not in plan["variants"] or run.get("config") != plan["variants"][name]:
        raise ValueError("Variant config mismatch")
    if run.get("actual_runtime") != dict(device=plan["device"], compute=plan["compute"], cpu_threads=plan["cpu_threads"]):
        raise ValueError("Actual runtime mismatch")
    if not isinstance(run.get("decoder_defaults"), dict) or not run["decoder_defaults"]:
        raise ValueError("Missing decoder defaults")
    expected = {(e["clip_id"], r): e for e in entries for r in range(plan["repeats"])}
    seen = set()
    for item in run.get("utterances", []):
        key = (item.get("clip_id"), item.get("repeat"))
        if key not in expected or key in seen or type(item.get("repeat")) is not int:
            raise ValueError("Duplicate/unexpected clip/repeat")
        seen.add(key)
        e = expected[key]
        if item.get("audio_sha256") != e["audio_sha256"] or item.get("duration_s") != e["duration_s"]:
            raise ValueError("Audio identity/duration mismatch")
        if any(not isinstance(item.get(k), str) for k in ("raw", "filtered", "cleaned")):
            raise ValueError("Missing transcript stage")
        if "[Transcription Error:" in item["raw"] or "[Transcription Error:" in item["cleaned"]:
            raise ValueError("Failed transcription")
        for k in ("processing_s", "compute_s", "rtf"):
            if not isinstance(item.get(k), (int, float)) or not math.isfinite(item[k]) or item[k] < 0:
                raise ValueError("Invalid timing")
        chunks, prompts, times, calls = (item.get(k) for k in ("raw_chunks", "prompts", "chunk_compute_s", "decoder_calls"))
        if any(not isinstance(v, list) for v in (chunks, prompts, times, calls)) or len({len(v) for v in (chunks, prompts, times, calls)}) != 1:
            raise ValueError("Incomplete chunk trace")
        if any(not isinstance(t, str) for t in chunks + prompts) or " ".join(chunks) != item["raw"]:
            raise ValueError("Invalid chunk text trace")
        if any(not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0 for t in times):
            raise ValueError("Invalid chunk timing")
        if not math.isclose(sum(times), item["compute_s"], abs_tol=1e-8) or not math.isclose(item["compute_s"]/e["duration_s"], item["rtf"], abs_tol=1e-8):
            raise ValueError("Inconsistent timing totals")
        c = run["config"]
        for call in calls:
            if any(call.get(k) != v for k, v in dict(beam_size=c["beam"], patience=c["patience"],
                    language="en", task="transcribe", condition_on_previous_text=False,
                    vad_filter=True, vad_parameters=plan["pipeline"]["vad_parameters"], without_timestamps=True).items()):
                raise ValueError("Decoder call mismatch")
            if type(call.get("max_new_tokens")) is not int or not 24 <= call["max_new_tokens"] <= 448:
                raise ValueError("Invalid decoder token cap")
    if seen != set(expected):
        raise ValueError("Missing clips; refusing partial comparison")


def paired_deltas(baseline, candidate, entries):
    """Exact count/rate deltas, aligned by clip/repeat, not means of rounded WER."""
    from eval_metrics import breakdown
    from score_asr_trial import entry_names
    by_id = {e["clip_id"]: e for e in entries}
    paired = {}
    for stage in ("raw", "cleaned"):
        lookup = {(i["clip_id"], i["repeat"]): i for i in baseline["utterances"]}
        rows, base_errors, candidate_errors, words = [], 0, 0, 0
        for item in candidate["utterances"]:
            key = (item["clip_id"], item["repeat"])
            e = by_id[key[0]]
            ref = e.get("spoken", e["reference"]) if stage == "raw" else e["reference"]
            before = breakdown(ref, lookup[key][stage], names=entry_names(e))
            after = breakdown(ref, item[stage], names=entry_names(e))
            words += before.words
            base_errors += before.errors
            candidate_errors += after.errors
            rows.append(dict(clip_id=key[0], repeat=key[1], words=before.words,
                             baseline_errors=before.errors, candidate_errors=after.errors,
                             delta_errors=after.errors-before.errors))
        paired[stage] = dict(words=words, baseline_errors=base_errors, candidate_errors=candidate_errors,
                             delta_errors=candidate_errors-base_errors,
                             delta_wer_pp=100*(candidate_errors-base_errors)/words if words else None,
                             improved=sum(r["delta_errors"] < 0 for r in rows),
                             worsened=sum(r["delta_errors"] > 0 for r in rows),
                             unchanged=sum(r["delta_errors"] == 0 for r in rows), utterances=rows)
    return paired


def compare(args):
    out = local_result_path(args.out)
    if out.exists():
        raise ValueError("Refusing to overwrite comparison")
    plan = json.loads(local_result_path(args.plan).read_text(encoding="utf-8"))
    entries = validate_plan(plan)
    if plan["versions"].get("wordfreq") != "3.1.1":
        raise ValueError("Scorer requires frozen wordfreq 3.1.1")
    runs = {}
    for path in args.run:
        run = json.loads(local_result_path(path).read_text(encoding="utf-8"))
        validate_run(run, plan, entries)
        if run["variant"] in runs:
            raise ValueError("Duplicate variant")
        runs[run["variant"]] = run
    if set(runs) != set(plan["variants"]):
        raise ValueError("All planned variants required; refusing incomplete matrix")
    defaults = runs["baseline"]["decoder_defaults"]
    if any(r["decoder_defaults"] != defaults for r in runs.values()):
        raise ValueError("Uncontrolled decoder default differences")
    from score_asr_trial import score_run
    scores = {n: score_run(r, entries) for n, r in runs.items()}
    deltas = {n: paired_deltas(runs["baseline"], r, entries) for n, r in runs.items() if n != "baseline"}
    validate_plan(plan)
    write_json(out, dict(schema=SCHEMA, kind="comparison", plan=plan,
                         run_sha256={n: r["record_sha256"] for n, r in runs.items()},
                         scores=scores, paired_deltas=deltas,
                         interpretation="Candidate minus baseline; negative error delta favors candidate. "
                         "Current-feature ablations, not historical regression proof; repeats are not independent clips."))
    for name, stages in deltas.items():
        for stage, d in stages.items():
            print(f"{name} {stage}: delta errors {d['delta_errors']}, reference words {d['words']}, "
                  f"improved/worsened/unchanged {d['improved']}/{d['worsened']}/{d['unchanged']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="Freeze inputs/settings without loading any model")
    p.add_argument("--manifest", action="append", required=True, type=Path)
    p.add_argument("--only")
    p.add_argument("--model-path", required=True, type=Path, help="Existing local CTranslate2 model directory")
    p.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    p.add_argument("--compute", choices=("int8_float32", "int8_float16", "int8", "float32", "float16"), default="int8_float32")
    p.add_argument("--cpu-threads", type=int, choices=range(1, 65), default=8)
    p.add_argument("--variants", default=DEFAULT_VARIANTS, help=", ".join(OVERRIDES))
    p.add_argument("--repeats", type=int, default=1)
    p.add_argument("--max-clips", type=int, default=100)
    p.add_argument("--max-audio-s", type=float, default=1800)
    p.add_argument("--timeout-s", type=int, default=1800, help="Hard wall timeout per variant, including load")
    p.add_argument("--out", required=True, type=Path)
    r = sub.add_parser("run", help="Run one selected variant in a bounded process")
    r.add_argument("--plan", required=True, type=Path)
    r.add_argument("--variant", required=True, choices=tuple(OVERRIDES))
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--execute", action="store_true")
    r.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    c = sub.add_parser("compare", help="Validate full matrix and score locally without inference")
    c.add_argument("--plan", required=True, type=Path)
    c.add_argument("--run", action="append", required=True, type=Path)
    c.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        {"plan": make_plan, "run": run_variant, "compare": compare}[args.command](args)
    except Exception:
        # Never print exception contents: third-party failures may include transcript text.
        print("Ablation rejected: stale/incomplete input, unavailable runtime, or bounded execution failure. "
              "Check the frozen plan and incomplete local run; no transcript printed.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
