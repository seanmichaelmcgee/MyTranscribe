"""
ablate_decoding.py — change one decoding/prompt setting at a time and score it.

Runs every recording in one or more manifests through the app's real pipeline
(ChunkedTranscriber chunking, prompt strategy, spelling corrector, voice commands)
and reports, per setting:

  WER          word error rate with names ignored (re-spelled names are free)
  med          error rate on medical words only (rare words from the vocabulary + key terms)
  common       error rate on everyday words
  invented     rare words in the output that were never said, per 100 words (confabulation)
  terms        key terms present;  format: line breaks/quotes/numbering right
  fallback     chunks where Whisper re-decoded with random sampling (temperature > 0)
  wait         mean seconds per short recording (= Stop -> text for snippets)

Settings are named presets (see PRESETS) or "base+key=value,key=value". Keys:
  model, compute, beam, prompt (none|tail|style|list|short), vad (0/1),
  stamps (0/1: timestamp mode; 1 = without_timestamps=False), temps (default|zero|short), fix (0/1)

    venv1060\\Scripts\\python.exe scripts\\ablate_decoding.py --manifest results_1060\\real_headset\\manifest.json ^
        --settings base,beam1,prompt-none --json results_1060\\ablation.json --show-invented

Fictional/synthetic or user-provided practice audio only.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
from wordfreq import zipf_frequency  # noqa: E402

from bench_engine import load_wav                                         # noqa: E402
from chunked_transcriber import ChunkedTranscriber, build_prompt, SAMPLE_RATE as SR   # noqa: E402
from eval_dictation import FiniteStream                                    # noqa: E402
from eval_metrics import Breakdown, breakdown, load_medical_words, normalize_words, term_hits   # noqa: E402
from fw_engine import FasterWhisperEngine, VAD_PARAMETERS, register_cuda_dll_dirs        # noqa: E402
from hw_profile import EngineConfig                                       # noqa: E402
from make_snippets import NAMES                                           # noqa: E402
from prompt_loader import load_prompt                                     # noqa: E402
from vocab import PromptBuilder, build_text_pipeline, load_lexicon, make_wordfreq_is_common   # noqa: E402
import voice_commands                                                     # noqa: E402

BASE = dict(model="large-v3", compute="int8_float32", beam=5, prompt="list", vad=1, stamps=0,
            temps="default", fix=1)
PRESETS = {
    "base": {},
    "beam1": {"beam": 1},
    "prompt-none": {"prompt": "none"},
    "prompt-tail": {"prompt": "tail"},
    "prompt-style": {"prompt": "style"},
    "prompt-short": {"prompt": "short"},
    "vad-off": {"vad": 0},
    "stamps": {"stamps": 1},
    "temp-zero": {"temps": "zero"},
    "temp-short": {"temps": "short"},
    "fp16": {"compute": "float16"},
    "nofix": {"fix": 0},
    "turbo": {"model": "large-v3-turbo"},
}
TEMPS = {"default": None, "zero": 0.0, "short": (0.0, 0.2, 0.4)}


def parse_setting(spec: str) -> dict:
    name, _, extra = spec.partition("+")
    cfg = dict(BASE, **PRESETS[name])
    for kv in filter(None, extra.split(",")):
        k, v = kv.split("=")
        cfg[k] = int(v) if v.isdigit() else v
    return cfg


class AblationEngine:
    """Engine for ChunkedTranscriber with explicit decode settings; records segment stats."""

    def __init__(self, fw: FasterWhisperEngine, cfg: dict):
        self.fw, self.cfg = fw, cfg
        self.fallbacks = 0
        self.calls = 0

    def count_tokens(self, text):
        return self.fw.count_tokens(text)

    def transcribe(self, audio, prompt=None):
        c = self.cfg
        cap = self.fw.max_new_tokens(len(audio) / SR, prompt)
        kw = dict(language="en", task="transcribe", beam_size=c["beam"], initial_prompt=prompt or None,
                  condition_on_previous_text=False, vad_filter=bool(c["vad"]),
                  without_timestamps=not c["stamps"], max_new_tokens=cap)
        if c["vad"]:
            kw["vad_parameters"] = VAD_PARAMETERS
        if TEMPS[c["temps"]] is not None:
            kw["temperature"] = TEMPS[c["temps"]]
        segs, _ = self.fw.model.transcribe(audio.astype(np.float32), **kw)
        segs = list(segs)
        self.calls += 1
        self.fallbacks += sum(1 for s in segs if getattr(s, "temperature", 0) and s.temperature > 0)
        return " ".join(s.text.strip() for s in segs if s.text.strip())


def make_prompting(kind: str, style: str, lex, count):
    """(base_prompt, prompt_builder) for a prompt strategy."""
    if kind == "none":
        return "", (lambda ctx: "")
    if kind == "tail":
        return "", (lambda ctx: build_prompt("", ctx))
    if kind == "style":
        return style, None
    budget = None if kind == "list" else count(style) + 45        # "short": ~10-12 terms
    kwargs = {} if budget is None else {"budget": budget}
    return style, PromptBuilder(style, lex, count=count, is_common=make_wordfreq_is_common(), **kwargs)


def entry_names(e) -> list:
    if e.get("names"):
        return e["names"]
    try:
        return NAMES.get(int(e.get("scenario", "x_")[:2]), [])
    except ValueError:
        return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", action="append", required=True, type=Path)
    ap.add_argument("--settings", default="base")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--show-invented", action="store_true", help="list invented / missed words (fictional data)")
    args = ap.parse_args(argv)

    register_cuda_dll_dirs()
    entries = []
    for m in args.manifest:
        for e in json.loads(m.read_text(encoding="utf-8")):
            e = dict(e)
            e["_path"] = m.parent / e["audio"]
            entries.append(e)
    zipf = lambda w: zipf_frequency(w, "en")
    import vocab as vocab_mod
    medical = load_medical_words(list(vocab_mod.DEFAULT_LEXICON_FILES) + list(vocab_mod.CORRECTION_ONLY_FILES),
                                 zipf=zipf)
    style = load_prompt()
    lex = load_lexicon(env={})
    _, corrector = build_text_pipeline(style, env={})     # same post-processing chain as the app
    audio_cache = {}

    specs = [s.strip() for s in args.settings.split(",") if s.strip()]
    cfgs = [(s, parse_setting(s)) for s in specs]
    engines = {}
    results = {}
    for spec, cfg in cfgs:
        key = (cfg["model"], cfg["compute"])
        if key not in engines:
            engines.clear()                                   # one model in VRAM at a time
            fw = FasterWhisperEngine(EngineConfig(cfg["model"], "cuda", cfg["compute"], 2, "ablation"))
            fw.warmup()
            engines[key] = fw
        fw = engines[key]
        eng = AblationEngine(fw, cfg)
        base_prompt, builder = make_prompting(cfg["prompt"], style, lex, fw.count_tokens)
        post = corrector if cfg["fix"] else None
        by_cat = defaultdict(Breakdown)
        terms = defaultdict(lambda: [0, 0])
        fmt = defaultdict(lambda: [0, 0])
        waits = defaultdict(list)
        per_utt = []
        for e in entries:
            if isinstance(builder, PromptBuilder):
                builder._rotation.clear()
            if e["_path"] not in audio_cache:
                audio_cache[e["_path"]] = load_wav(e["_path"])
            audio = audio_cache[e["_path"]]
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
            t = ChunkedTranscriber(eng, base_prompt, stream_factory=lambda: (FiniteStream(pcm), None),
                                   prompt_builder=builder, postprocess=post)
            t0 = time.perf_counter()
            t.start_recording()
            t._capture_thread.join()
            t.stop_recording()
            t.wait_until_idle()
            secs = time.perf_counter() - t0
            hyp = voice_commands.apply(t.text)
            ref = e["reference"]
            key_terms = e.get("terms", [])
            term_words = {w for term in key_terms for w in normalize_words(term) if zipf(w) < 4.0}
            is_med = lambda w: w in medical or w in term_words
            b = breakdown(ref, hyp, names=entry_names(e), is_medical=is_med, zipf=zipf)
            cat = e.get("category") or e.get("profile") or "all"
            for k in (cat, "ALL"):
                by_cat[k].add(b)
            found, miss = term_hits(key_terms, hyp)
            for k in (cat, "ALL"):
                terms[k][0] += len(found)
                terms[k][1] += len(found) + len(miss)
                if "\n" in ref or '"' in ref:
                    fmt[k][1] += 1
                    fmt[k][0] += hyp.count("\n") == ref.count("\n") and hyp.count('"') == ref.count('"')
                if len(audio) / SR < 20:
                    waits[k].append(secs)
            per_utt.append({"audio": e["audio"], "hyp": hyp, **b.rates(), "invented": b.invented,
                            "medical_missed": b.medical_missed})
        summary = {}
        print(f"\n== {spec}: {cfg['model']} {cfg['compute']} beam {cfg['beam']} prompt={cfg['prompt']} "
              f"vad={cfg['vad']} stamps={cfg['stamps']} temps={cfg['temps']} fix={cfg['fix']} "
              f"| fallback chunks {eng.fallbacks}/{eng.calls}")
        print(f"{'category':9s} {'WER':>6s} {'med':>6s} {'common':>7s} {'invented':>9s} {'terms':>6s} "
              f"{'format':>7s} {'wait':>6s}")
        for k in sorted(by_cat, key=lambda c: (c == "ALL", c)):
            r = by_cat[k].rates()
            tr = round(100 * terms[k][0] / terms[k][1], 1) if terms[k][1] else 0.0
            ft = f"{fmt[k][0]}/{fmt[k][1]}" if fmt[k][1] else "-"
            wt = round(float(np.mean(waits[k])), 2) if waits[k] else 0.0
            summary[k] = dict(r, terms=tr, format=ft, wait=wt)
            print(f"{k:9s} {r['wer']:6.1f} {r['medical_wer']:6.1f} {r['common_wer']:7.1f} "
                  f"{r['invented_per_100']:9.1f} {tr:6.1f} {ft:>7s} {wt:6.2f}")
        if args.show_invented:
            allb = by_cat["ALL"]
            print(f"  invented: {', '.join(allb.invented) or '-'}")
            print(f"  medical missed: {', '.join(allb.medical_missed) or '-'}")
        results[spec] = {"config": cfg, "fallbacks": eng.fallbacks, "calls": eng.calls,
                         "summary": summary, "utterances": per_utt}
    if args.json:
        args.json.write_text(json.dumps(results, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
