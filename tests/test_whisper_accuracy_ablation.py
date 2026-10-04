"""CPU-only guards for controls, real chunk flow, provenance, and paired scoring.

No inference runtime imported. Scoring tests inject a deterministic frequency
function to test arithmetic/name policy without requiring native dependencies.
"""
import copy
import json
import subprocess
import sys
import types
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import asr_trial_common as common
import whisper_accuracy_ablation as ab
from fw_engine import FasterWhisperEngine
from hw_profile import EngineConfig
from vocab import Lexicon, PostProcess, PromptBuilder, Term, Topic


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    root = tmp_path
    local = root / "results_fixture"
    local.mkdir()
    monkeypatch.setattr(common, "ROOT", root)
    monkeypatch.setattr(ab, "ROOT", root)
    # The common helper's gitignore decision is separately covered below.
    monkeypatch.setattr(common.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(ab, "source_revision", lambda: "frozen-head")
    monkeypatch.setattr(ab, "source_hashes", lambda: {"src/fw_engine.py": "source-v1"})
    monkeypatch.setattr(ab, "experiment_sources", lambda: {"scripts/whisper_accuracy_ablation.py": "own-v1"})
    monkeypatch.setattr(ab, "runtime_versions", lambda: dict(python="test", platform="test", **{
        p: "3.1.1" if p == "wordfreq" else "test" for p in ab.PACKAGES}))
    model = root / "existing_model"
    model.mkdir()
    for name in ("model.bin", "config.json", "tokenizer.json"):
        (model / name).write_bytes(name.encode())
    audio = local / "clip.wav"
    with wave.open(str(audio), "wb") as w:
        w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        w.writeframes(np.full(1600, 900, dtype="<i2").tobytes())
    manifest = local / "manifest.json"
    manifest.write_text(json.dumps([dict(audio="clip.wav", reference="Dr Alice renal normal.\nReview.",
        spoken="Dr Alice renal normal. New line. Review.", names=["Alice"], terms=["renal"], category="result")]))
    args = SimpleNamespace(out=local / "plan.json", manifest=[manifest], only=None, variants="baseline,no-corrector",
        repeats=1, max_clips=100, max_audio_s=1800, timeout_s=1800, model_path=model,
        device="cpu", compute="int8", cpu_threads=2)
    plan = ab.make_plan(args)
    entries = ab.validate_plan(plan)
    return args, plan, entries


def signed_run(plan, entries, name="baseline"):
    c = plan["variants"][name]
    utterances = []
    for repeat in range(plan["repeats"]):
        for e in entries:
            raw, cleaned = e["spoken"], e["reference"]
            call = dict(beam_size=c["beam"], patience=c["patience"], language="en", task="transcribe",
                condition_on_previous_text=False, vad_filter=True, vad_parameters=plan["pipeline"]["vad_parameters"],
                without_timestamps=True, max_new_tokens=24)
            utterances.append(dict(clip_id=e["clip_id"], repeat=repeat, duration_s=e["duration_s"],
                audio_sha256=e["audio_sha256"], raw=raw, filtered=raw, cleaned=cleaned,
                raw_chunks=[raw], prompts=["bundled style"], chunk_compute_s=[0.01], decoder_calls=[call],
                processing_s=0.1, compute_s=0.01, rtf=0.01/e["duration_s"]))
    run = {k: copy.deepcopy(plan[k]) for k in ("plan_sha256", "corpus_sha256", "source_sha256", "experiment_sha256", "versions", "model", "repeats")}
    run.update(schema=ab.SCHEMA, kind="run", completed=True, variant=name, config=c,
        utterances=utterances, decoder_defaults={"temperature": [0.0, 0.2]},
        actual_runtime=dict(device=plan["device"], compute=plan["compute"], cpu_threads=plan["cpu_threads"]))
    run["record_sha256"] = ab.fingerprint(run, "record_sha256")
    return run


def resign(run):
    run["record_sha256"] = ab.fingerprint(run, "record_sha256")


def test_plan_is_read_only_with_respect_to_models_and_is_frozen(frozen):
    args, plan, entries = frozen
    assert plan["variants"]["baseline"] == ab.BASE
    assert ab.validate_plan(plan) == entries
    assert plan["model"]["sha256"]["model.bin"] == common.sha256(args.model_path / "model.bin")
    assert "faster_whisper" not in sys.modules
    with pytest.raises(ValueError, match="overwrite"):
        ab.make_plan(args)


@pytest.mark.parametrize("change", ["common-source", "own-source", "version", "model", "reference", "names", "audio", "plan"])
def test_stale_plan_rejected(frozen, monkeypatch, change):
    args, plan, entries = frozen
    if change == "common-source":
        monkeypatch.setattr(ab, "source_hashes", lambda: {"different": "hash"})
    elif change == "own-source":
        monkeypatch.setattr(ab, "experiment_sources", lambda: {"different": "hash"})
    elif change == "version":
        monkeypatch.setattr(ab, "runtime_versions", lambda: {})
    elif change == "model":
        (args.model_path / "model.bin").write_bytes(b"new weights")
    elif change == "audio":
        with wave.open(str(entries[0]["_path"]), "wb") as w:
            w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            w.writeframes(np.full(1600, 901, dtype="<i2").tobytes())
    elif change in ("reference", "names"):
        rows = json.loads(args.manifest[0].read_text())
        rows[0][change] = "changed" if change == "reference" else ["another name"]
        args.manifest[0].write_text(json.dumps(rows))
    else:
        plan["variants"]["baseline"]["beam"] = 1
    with pytest.raises(ValueError):
        ab.validate_plan(plan)


@pytest.mark.parametrize("change", ["unfinished", "missing", "duplicate", "unexpected", "audio", "config", "source", "own-source", "version", "model", "transcript", "fallback", "trace", "decoder", "nan", "totals", "tamper"])
def test_incomplete_or_mislabeled_runs_rejected(frozen, change):
    _, plan, entries = frozen
    run = signed_run(plan, entries)
    ab.validate_run(run, plan, entries)
    item = run["utterances"][0]
    if change == "unfinished": run["completed"] = False
    if change == "missing": run["utterances"] = []
    if change == "duplicate": run["utterances"] *= 2
    if change == "unexpected": item["repeat"] = 5
    if change == "audio": item["audio_sha256"] = "changed"
    if change == "config": run["config"] = dict(run["config"], corrector=False)
    if change == "source": run["source_sha256"] = {}
    if change == "own-source": run["experiment_sha256"] = {}
    if change == "version": run["versions"] = {}
    if change == "model": run["model"] = {}
    if change == "transcript": del item["cleaned"]
    if change == "fallback": run["actual_runtime"]["device"] = "cuda"
    if change == "trace": item["prompts"] = []
    if change == "decoder": item["decoder_calls"][0]["patience"] = 1
    if change == "nan": item["rtf"] = float("nan")
    if change == "totals": item["compute_s"] *= 2
    if change == "tamper": item["cleaned"] = "tampered"
    if change != "tamper": resign(run)
    with pytest.raises(ValueError):
        ab.validate_run(run, plan, entries)


def test_bounds_do_not_silently_truncate(frozen):
    _, _, entries = frozen
    with pytest.raises(ValueError, match="exceeds bounds"):
        ab.check_bounds(entries, ["baseline"], 1, 1, 0.01, 10)
    with pytest.raises(ValueError): ab.check_bounds(entries, ["baseline", "baseline"], 1, 5, 10, 10)
    with pytest.raises(ValueError): ab.check_bounds(entries, ["baseline"], 4, 5, 10, 10)
    with pytest.raises(ValueError): ab.check_bounds(entries, ["baseline"], 1, 5, float("nan"), 10)
    with pytest.raises(ValueError): ab.check_bounds(entries, ["baseline"], 1, 5, 10, 7201)


def test_existing_local_model_and_ignored_output_required(frozen, monkeypatch):
    args, _, _ = frozen
    with pytest.raises(ValueError): ab.model_integrity(args.model_path / "not-present")
    with pytest.raises(ValueError): ab.local_result_path(args.out.parent.parent / "tracked.json")
    monkeypatch.setattr(common.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1))
    with pytest.raises(ValueError, match="gitignored"): ab.local_result_path(args.out)


def test_run_requires_opt_in_and_timeout_kills_variant(frozen, monkeypatch):
    args, plan, _ = frozen
    run_args = SimpleNamespace(plan=args.out, out=args.out.parent / "run.json", variant="baseline", execute=False, worker=False)
    with pytest.raises(ValueError, match="opt-in"): ab.run_variant(run_args)
    run_args.execute = True
    def timeout(command, **kwargs):
        assert kwargs["timeout"] == plan["bounds"]["timeout_s"]
        assert command[command.index("--variant")+1] == "baseline"
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    monkeypatch.setattr(ab.subprocess, "run", timeout)
    # Validate inputs before substituting subprocess: common uses the same module.
    monkeypatch.setattr(ab, "validate_plan", lambda p: [])
    monkeypatch.setattr(ab, "local_result_path", lambda p: p)
    with pytest.raises(ValueError, match="timed out"): ab.run_variant(run_args)


def pipeline_factory(style, count=None, env=None, correction_files=None):
    assert env == {}
    assert len(correction_files) == 1 and correction_files[0].name == "corrections.txt"
    lex = Lexicon(topics={"renal": Topic("renal", triggers=["kidney"], terms=[Term("apixaban", "drug", "renal")])})
    return PromptBuilder(style, lex, count=count), PostProcess(lambda t: t.replace("badterm", "kidney"),
                                                            lambda t: t.replace("H-E-E-N-T", "HEENT"))


def test_independent_controls_and_consistent_context_tail():
    for name, correct, fix in (("baseline", True, True), ("no-corrector", False, True),
                               ("no-fixes", True, False), ("no-post", False, False)):
        _, post = ab.make_pipeline("style", len, ab.variant_config(name), factory=pipeline_factory)
        assert post("badterm H-E-E-N-T") == ("kidney" if correct else "badterm") + " " + ("HEENT" if fix else "H-E-E-N-T")
    base, _ = ab.make_pipeline("style", lambda s: 1, ab.BASE, factory=pipeline_factory)
    off, _ = ab.make_pipeline("style", lambda s: 1, ab.variant_config("no-topics"), factory=pipeline_factory)
    assert "Vocabulary:" in base("kidney")
    assert off("kidney") == "style kidney"
    context = "prior word " * 40
    assert off(context) == PromptBuilder("style", Lexicon(), count=lambda s: 1)(context)
    none, _ = ab.make_pipeline("style", len, ab.variant_config("no-prompt"), factory=pipeline_factory)
    assert none("kidney") == ""
    style, _ = ab.make_pipeline("style", len, ab.variant_config("style-only"), factory=pipeline_factory)
    assert style("kidney") == "style"


def test_corrector_unavailable_is_not_labeled_enabled():
    def missing(*a, **kw):
        return PromptBuilder("style", Lexicon()), PostProcess(None, lambda t: t)
    with pytest.raises(ValueError, match="dependency unavailable"):
        ab.make_pipeline("style", len, ab.BASE, factory=missing)


class FakeModel:
    def __init__(self, *a, **kw):
        self.calls = []

    def transcribe(self, audio, temperature=(0.0, 0.2), **kwargs):
        self.calls.append(kwargs)
        return iter([SimpleNamespace(text=" badterm H-E-E-N-T ")]), None


@pytest.mark.parametrize("name", ["baseline", "greedy", "beam-patience1"])
def test_decoder_uses_production_options_with_patience_override(name):
    cfg = ab.variant_config(name)
    fw = FasterWhisperEngine(EngineConfig("existing", "cpu", "int8", 2, "fake"), model_factory=FakeModel, beam_size=cfg["beam"])
    model = fw.model
    fw.model = ab.DecoderProxy(model, cfg["patience"])
    assert fw.transcribe(np.ones(1600, dtype=np.float32), "style") == "badterm H-E-E-N-T"
    call = model.calls[0]
    assert call["beam_size"] == cfg["beam"] and call["patience"] == cfg["patience"]
    assert call["condition_on_previous_text"] is False and call["vad_filter"] is True
    assert call["initial_prompt"] == "style" and call["max_new_tokens"] == fw.max_new_tokens(.1, "style")
    assert "initial_prompt" not in fw.model.calls[0]
    assert fw.model.defaults["temperature"] == [0.0, 0.2]


def test_real_chunk_flow_uses_previous_corrected_text_not_reference(frozen, monkeypatch):
    _, _, entries = frozen
    with wave.open(str(entries[0]["_path"]), "wb") as w:
        w.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        w.writeframes(np.full(40000, 900, dtype="<i2").tobytes())
    clip = ab.audio_inputs(entries)[0]
    clip["duration_s"] = 2.5
    assert set(clip) == {"clip_id", "audio", "audio_sha256", "duration_s", "_path"}
    original = ab.make_pipeline
    monkeypatch.setattr(ab, "make_pipeline", lambda s, count, c: original(s, count, c, factory=pipeline_factory))
    fw = FasterWhisperEngine(EngineConfig("existing", "cpu", "int8", 2, "fake"), model_factory=FakeModel)
    cfg = dict(ab.BASE, chunk_s=1.0)
    item = ab.replay_clip(clip, fw, cfg, "style")
    assert len(item["prompts"]) >= 2
    assert item["prompts"][0] == "style"
    assert "kidney HEENT" in item["prompts"][1]
    assert "Vocabulary:" in item["prompts"][1]
    assert "Alice" not in " ".join(item["prompts"])
    assert item["raw"].startswith("badterm H-E-E-N-T")
    assert item["cleaned"].startswith("kidney HEENT")
    assert item["stop_to_text_s"] is None


def test_swallowed_postprocess_failure_refuses_score(frozen, monkeypatch):
    _, _, entries = frozen
    def fail(text): raise RuntimeError("sensitive text must never be printed")
    monkeypatch.setattr(ab, "make_pipeline", lambda *a: (lambda ctx: "style", fail))
    fw = FasterWhisperEngine(EngineConfig("existing", "cpu", "int8", 2, "fake"), model_factory=FakeModel)
    with pytest.raises(ValueError, match="failed pipeline"):
        ab.replay_clip(ab.audio_inputs(entries)[0], fw, ab.BASE, "style")


@pytest.fixture
def scorer(monkeypatch):
    freq = types.ModuleType("wordfreq")
    freq.zipf_frequency = lambda w, lang: 2.0 if w.lower() == "renal" else 5.0
    monkeypatch.setitem(sys.modules, "wordfreq", freq)
    # Keep this fixture's synthetic frequency function isolated from other tests.
    monkeypatch.delitem(sys.modules, "score_asr_trial", raising=False)
    import score_asr_trial
    return score_asr_trial


def test_paired_scoring_preserves_names_and_spoken_vs_written(frozen, scorer):
    _, plan, entries = frozen
    base = signed_run(plan, entries)
    candidate = signed_run(plan, entries, "no-corrector")
    scores = scorer.score_run(base, entries)
    assert scores["raw"]["summary"]["ALL"]["wer"] == 0
    assert scores["cleaned"]["summary"]["ALL"]["wer"] == 0
    candidate["utterances"][0]["raw"] = "Dr Bob renal normal. New line. Review."
    candidate["utterances"][0]["cleaned"] = "Dr Bob renal normal.\nReview."
    assert ab.paired_deltas(base, candidate, entries)["cleaned"]["delta_errors"] == 0
    candidate["utterances"][0]["cleaned"] = "Dr Bob renal abnormal.\nReview."
    result = ab.paired_deltas(base, candidate, entries)["cleaned"]
    assert result["delta_errors"] == 1 and result["worsened"] == 1
    assert result["words"] == 3 and result["delta_wer_pp"] == pytest.approx(100/3)


def test_full_matrix_required_and_compare_never_relabels_fingerprints(frozen, scorer):
    args, plan, entries = frozen
    paths = []
    for name in plan["variants"]:
        path = args.out.parent / (name + ".json")
        common.write_json(path, signed_run(plan, entries, name))
        paths.append(path)
    compare_args = SimpleNamespace(plan=args.out, run=paths[:1], out=args.out.parent / "comparison.json")
    with pytest.raises(ValueError, match="All planned variants"):
        ab.compare(compare_args)
    assert not compare_args.out.exists()
    compare_args.run = paths
    before = {p: p.read_bytes() for p in paths}
    ab.compare(compare_args)
    report = json.loads(compare_args.out.read_text())
    assert report["plan"] == plan
    assert report["paired_deltas"]["no-corrector"]["raw"]["delta_errors"] == 0
    assert all(p.read_bytes() == data for p, data in before.items())
    assert report["scores"]["baseline"]["cleaned"]["summary"]["ALL"]["counts"]["words"] == 3


def test_source_manifest_includes_harness_independent_of_common():
    hashes = ab.experiment_sources()
    assert hashes["scripts/whisper_accuracy_ablation.py"] == common.sha256(Path(ab.__file__))
    assert "src/eval_metrics.py" in hashes


def test_cli_failure_prints_no_sensitive_exception(monkeypatch, capsys):
    monkeypatch.setattr(ab, "make_plan", lambda a: (_ for _ in ()).throw(ValueError("private transcript")))
    assert ab.main(["plan", "--manifest", "unused", "--model-path", "unused", "--out", "unused"]) == 2
    assert "private transcript" not in capsys.readouterr().err
