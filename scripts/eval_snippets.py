"""
eval_snippets.py — accuracy and speed on short clinical snippets, per model setting.

For each setting (model / compute type / beam) it transcribes every snippet the way
the app does (topic prompts + spelling correction + voice commands) and reports,
per category (message / result / exam):

  WER %            word error rate against the expected written text
  terms %          key terms present
  format %         line breaks and quotes match (snippets that use voice commands)
  wait s           mean / max transcription time per snippet. Snippets are shorter
                   than one chunk, so this is the wait between Stop and the text.

    venv1060\\Scripts\\python.exe scripts\\eval_snippets.py --manifest results_1060\\snippets\\manifest.json ^
        --settings large-v3-turbo,large-v3,large-v3:b1 --json results_1060\\snippets_eval.json

A setting is model[:bN] (beam N, default 5); --compute-type applies to all.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bench_engine import load_wav                                   # noqa: E402
from eval_dictation import transcribe_file                         # noqa: E402
from eval_metrics import term_hits, word_error_rate                 # noqa: E402
from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs   # noqa: E402
from hw_profile import EngineConfig                                 # noqa: E402
from prompt_loader import load_prompt                               # noqa: E402
from vocab import build_text_pipeline                               # noqa: E402
import voice_commands                                               # noqa: E402


def parse_setting(s):
    model, _, beam = s.partition(":b")
    return model, int(beam) if beam else 5


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--settings", default="large-v3-turbo,large-v3")
    ap.add_argument("--compute-type", default="int8_float32")
    ap.add_argument("--show-text", action="store_true", help="print each transcript (fictional data only)")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)

    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    register_cuda_dll_dirs()
    style = load_prompt()
    summary = {}
    for setting in args.settings.split(","):
        model, beam = parse_setting(setting)
        eng = FasterWhisperEngine(EngineConfig(model, "cuda", args.compute_type, 2, "snippets"), beam_size=beam)
        eng.warmup()
        builder, corrector = build_text_pipeline(style, count=eng.count_tokens, env={})
        stats = defaultdict(lambda: {"err": 0.0, "words": 0, "hit": 0, "terms": 0, "fmt_ok": 0, "fmt_n": 0,
                                     "waits": []})
        print(f"\n== {model} beam {beam} {args.compute_type} ==")
        for e in entries:
            if builder is not None:
                builder._rotation.clear()
            audio = load_wav(args.manifest.parent / e["audio"])
            raw, secs = transcribe_file(eng, audio, style, builder, corrector)
            hyp = voice_commands.apply(raw)
            w, n = word_error_rate(e["reference"], hyp)
            found, miss = term_hits(e["terms"], hyp)
            ref = e["reference"]
            uses_format = "\n" in ref or '"' in ref
            fmt_ok = hyp.count("\n") == ref.count("\n") and hyp.count('"') == ref.count('"')
            for key in (e["category"], "ALL"):
                s = stats[key]
                s["err"] += w * n
                s["words"] += n
                s["hit"] += len(found)
                s["terms"] += len(found) + len(miss)
                s["waits"].append(secs)
                if uses_format:
                    s["fmt_n"] += 1
                    s["fmt_ok"] += fmt_ok
            flag = "" if not miss else f"  missed: {', '.join(miss)}"
            print(f"  {e['audio']:34s} {e['seconds']:5.1f}s  WER {w * 100:5.1f}%  wait {secs:4.2f}s{flag}")
            if args.show_text:
                print("      " + hyp.replace("\n", " ⏎ "))
        print(f"{'category':10s} {'WER %':>7s} {'terms %':>8s} {'format':>8s} {'wait mean':>10s} {'wait max':>9s}")
        summary[setting] = {}
        for cat in ("message", "result", "exam", "ALL"):
            s = stats[cat]
            if not s["words"]:
                continue
            row = {"wer": round(100 * s["err"] / s["words"], 1),
                   "terms": round(100 * s["hit"] / max(1, s["terms"]), 1),
                   "format": f"{s['fmt_ok']}/{s['fmt_n']}" if s["fmt_n"] else "-",
                   "wait_mean": round(sum(s["waits"]) / len(s["waits"]), 2),
                   "wait_max": round(max(s["waits"]), 2)}
            summary[setting][cat] = row
            print(f"{cat:10s} {row['wer']:7.1f} {row['terms']:8.1f} {row['format']:>8s} "
                  f"{row['wait_mean']:9.2f}s {row['wait_max']:8.2f}s")
        del eng
    if args.json:
        args.json.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
