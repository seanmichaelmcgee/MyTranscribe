"""
Baseline recognition in other languages on the public FLEURS test sets.

FLEURS (Google, CC BY 4.0) is read speech: sentences from Wikipedia-style text,
many speakers, about 10 seconds each. It says how well the recogniser hears a
language, not how well it handles medical dictation in it.

    fleurs_benchmark.py --root results_1060/fleurs --languages es_419,fr_fr,sw_ke --limit 300

--root holds <language>/test.tsv and <language>/test/*.wav as published at
huggingface.co/datasets/google/fleurs (data/<language>/). Evaluation only.
Scoring: lower-cased words with punctuation removed, against FLEURS'
raw_transcription. Numbers are compared as written, so "12" against "doce"
counts as an error; that inflates every language a little.
"""

import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

WHISPER_CODE = {"es_419": "es", "fr_fr": "fr", "sw_ke": "sw", "en_us": "en"}


def words(text: str) -> list:
    """Lower-case word tokens, any script; punctuation and symbols dropped, apostrophes kept inside words."""
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*", text, re.UNICODE)


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[len(b)]


def load_rows(folder: Path, limit: int) -> list:
    """[(wav path, reference text)] in file order, first `limit` whose audio exists."""
    rows = []
    for line in (folder / "test.tsv").read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        wav = folder / "test" / parts[1]
        if wav.is_file():
            rows.append((wav, parts[2]))
        if limit and len(rows) >= limit:
            break
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--languages", default="es_419,fr_fr,sw_ke")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--model")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    import dictation_reliability as dr
    from faster_whisper import decode_audio      # FLEURS audio is 32-bit float WAV
    engine = dr.make_engine("whisper", args.model)
    results = {}
    for name in args.languages.split(","):
        rows = load_rows(args.root / name, args.limit)
        if not rows:
            print(f"{name}: no audio found under {args.root / name}")
            continue
        engine.language = WHISPER_CODE.get(name, name.split("_")[0])
        errors = total = char_errors = chars = 0
        seconds, t0, texts = 0.0, time.perf_counter(), []
        for wav, reference in rows:
            audio = decode_audio(str(wav), sampling_rate=16000)
            seconds += len(audio) / 16000
            text = engine.transcribe(audio, None)
            ref, hyp = words(reference), words(text)
            errors += edit_distance(ref, hyp)
            total += len(ref)
            char_errors += edit_distance(list(" ".join(ref)), list(" ".join(hyp)))
            chars += len(" ".join(ref))
            texts.append({"file": wav.name, "reference": reference, "text": text})
        results[name] = {"utterances": len(rows), "audio_s": round(seconds), "words": total,
                         "wer": round(100 * errors / max(1, total), 2), "cer": round(100 * char_errors / max(1, chars), 2),
                         "compute_s": round(time.perf_counter() - t0), "rows": texts}
        r = results[name]
        print(f"{name}: {r['utterances']} utterances, {r['audio_s']} s audio, WER {r['wer']}%, CER {r['cer']}%, "
              f"{r['compute_s']} s compute", flush=True)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
