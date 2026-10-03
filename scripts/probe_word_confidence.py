"""
probe_word_confidence.py — do Whisper's word probabilities pick out the wrong words?

Transcribes each recording with word_timestamps=True (faster-whisper's second
alignment pass gives Word.probability), aligns the output with the reference,
and reports for several thresholds: how many wrong / invented words would be
flagged (recall) and how many flags are false alarms (precision). Also the extra
time the alignment pass costs. Practice / fictional audio only.

    venv1060\\Scripts\\python.exe scripts\\probe_word_confidence.py --manifest results_1060\\real_headset\\manifest.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np  # noqa: E402
from wordfreq import zipf_frequency  # noqa: E402

from bench_engine import load_wav                                       # noqa: E402
from eval_metrics import align, normalize_words                         # noqa: E402
from fw_engine import FasterWhisperEngine, VAD_PARAMETERS, register_cuda_dll_dirs   # noqa: E402
from hw_profile import EngineConfig                                     # noqa: E402
from prompt_loader import load_prompt                                   # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--beam", type=int, default=5)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    register_cuda_dll_dirs()
    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    fw = FasterWhisperEngine(EngineConfig(args.model, "cuda", "int8_float32", 2, "probe"))
    fw.warmup()
    style = load_prompt()
    labelled = []            # (probability, is_error, is_invented, word)
    t_plain = t_words = 0.0
    for e in entries:
        a = load_wav(args.manifest.parent / e["audio"]).astype(np.float32)
        common = dict(language="en", beam_size=args.beam, initial_prompt=style, condition_on_previous_text=False,
                      vad_filter=True, vad_parameters=VAD_PARAMETERS, without_timestamps=True,
                      max_new_tokens=fw.max_new_tokens(len(a) / 16000, style))
        t0 = time.perf_counter()
        list(fw.model.transcribe(a, **common)[0])
        t_plain += time.perf_counter() - t0
        t0 = time.perf_counter()
        segs = list(fw.model.transcribe(a, word_timestamps=True, **common)[0])
        t_words += time.perf_counter() - t0
        words = [w for s in segs for w in (s.words or [])]
        # Expand each Whisper word into normalised tokens (keeping its probability).
        hyp_tokens, probs, raw = [], [], []
        for w in words:
            for tok in normalize_words(w.word):
                hyp_tokens.append(tok)
                probs.append(w.probability)
                raw.append(w.word.strip())
        ref = normalize_words(e["reference"])
        ref_set = set(ref)
        status = ["ok"] * len(hyp_tokens)
        for op, ri, hj in align(ref, hyp_tokens):
            if hj is not None and op != "ok":
                status[hj] = op
        for tok, p, st, rw in zip(hyp_tokens, probs, status, raw):
            invented = st != "ok" and tok not in ref_set and tok.isalpha() and zipf_frequency(tok, "en") < 3.0
            labelled.append((p, st != "ok", invented, rw))
    n_err = sum(1 for x in labelled if x[1])
    n_inv = sum(1 for x in labelled if x[2])
    print(f"{len(labelled)} output words, {n_err} wrong, {n_inv} invented. "
          f"Alignment pass cost: {t_words - t_plain:+.1f} s over {t_plain:.1f} s ({100 * (t_words / t_plain - 1):+.0f}%)")
    print(f"{'threshold':>9s} {'flagged':>8s} {'wrong caught':>13s} {'invented caught':>16s} {'precision':>10s}")
    rows = []
    for th in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7):
        flagged = [x for x in labelled if x[0] < th]
        caught = sum(1 for x in flagged if x[1])
        inv = sum(1 for x in flagged if x[2])
        prec = 100 * caught / len(flagged) if flagged else 0.0
        rows.append(dict(threshold=th, flagged=len(flagged), wrong_caught=caught, invented_caught=inv,
                         precision=round(prec, 1)))
        print(f"{th:9.1f} {len(flagged):8d} {caught:6d}/{n_err:<6d} {inv:9d}/{n_inv:<6d} {prec:9.1f}%")
    print("\nInvented words and their probabilities:", [(x[3], round(x[0], 2)) for x in labelled if x[2]])
    print("Lowest-probability correct words:",
          [(x[3], round(x[0], 2)) for x in sorted(labelled) if not x[1]][:12])
    if args.json:
        args.json.write_text(json.dumps({"rows": rows, "words": labelled}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
