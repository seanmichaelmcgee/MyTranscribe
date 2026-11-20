"""
term_bench.py — does each model write classical medical terms correctly?

Synthetic voices read the short fictional notes in validation/term_set_en_v1.txt: eponymous signs,
syndromes and fractures, organisms, scores and drugs. Each clip is decoded the way the app decodes
a dictation (on large-v3 with a graphics card, or small.en on the processor), and every marked term
is looked for in what the app would write.

    term_bench.py plan   [--voices V01,V07]                        # no network, no cost
    term_bench.py make   --go [--voices ...] [--budget-usd 3]      # OpenAI voices: costs money
    term_bench.py check  --model <large-v3 folder>                 # can large-v3 hear each term when told it?
    term_bench.py run    --name gpu --model <folder> [--device cpu --threads 4 --pin 16-19]
    term_bench.py report --names gpu,cpu

The voice gets a pronunciation hint for foreign eponyms ("Charcot = shar-KOH"), but it can still
say a term wrongly. "check" decodes each clip on large-v3 with that clip's terms in the prompt:
a term that even this primed large-v3 does not write goes on a list for a person to listen to,
and is not counted for or against any model until then.

The audio is AI-generated, for testing and tuning only: never for training, never published
(docs/testing/README.md). It and every result stay out of the repository (--out).
"""

import argparse
import datetime as dt
import difflib
import hashlib
import json
import os
import re
import sys
import threading
import time
import unicodedata
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import synth_voices as sv  # noqa: E402

SET = ROOT / "validation" / "term_set_en_v1.txt"
OUT = ROOT / "results_1060" / "term_set" / "en_v1"
PROFILE = "some"        # settings_suite.PROFILES: what setup gives a speaker who talks naturally
_MARK = re.compile(r"\[\[(.+?)\]\]")


# ── The set ──────────────────────────────────────────────────────────────────
def parse_set(text: str):
    """(pronunciation hints {term: said}, items [{id, topic, split, lines, reference, targets}])."""
    hints, items, current = {}, [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or (line.startswith("#") and not line.startswith("##")):
            continue
        if line.startswith("## pronounce"):
            current = "hints"
            continue
        if line.startswith("## "):
            ident, topic, split = ([f.strip() for f in line[3:].split("|")] + ["", ""])[:3]
            current = {"id": ident, "topic": topic, "split": split, "lines": []}
            items.append(current)
            continue
        if current == "hints":
            term, _, said = line.partition("=")
            hints[term.strip()] = said.strip()
        elif current is not None:
            current["lines"].append(line)
    for it in items:
        marks = [[s.strip() for s in m.split("|")] for ln in it["lines"] for m in _MARK.findall(ln)]
        it["targets"] = [m[0] for m in marks]
        it["spellings"] = {m[0]: m for m in marks}      # [[cephalexin|cefalexin]]: either is right
        it["reference"] = "\n".join(_MARK.sub(lambda m: m.group(1).split("|")[0].strip(), ln)
                                    for ln in it["lines"])
    return hints, items


def load_set(path: Path = SET):
    return parse_set(path.read_text(encoding="utf-8"))


# ── Finding a term in text ───────────────────────────────────────────────────
def tokens(text: str, fold: bool = True) -> list:
    """Words for matching: lower case, accents and apostrophes dropped, hyphens split; with fold,
    a final s is dropped too, so "Homans' sign", "Homan's sign" and "Homans sign" all match."""
    text = unicodedata.normalize("NFKD", text.replace("’", "'"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower().replace("'", "")
    words = re.findall(r"[a-z0-9]+", text)
    return [w[:-1] if fold and len(w) >= 4 and w.endswith("s") else w for w in words]


def _find(needle: list, hay: list) -> int:
    for i in range(len(hay) - len(needle) + 1):
        if hay[i:i + len(needle)] == needle:
            return i
    return -1


def found(term: str, text: str) -> bool:
    """Is the term written in the text (as words; a multi-word term may also be run together)?"""
    want, have = tokens(term), tokens(text)
    if want and _find(want, have) >= 0:
        return True
    return len(want) > 1 and "".join(want) in "".join(have)


def written(item: dict, term: str, text: str) -> bool:
    """Is the term written in the text in any of its accepted spellings?"""
    return any(found(s, text) for s in item["spellings"].get(term, [term]))


def heard_as(reference: str, term: str, text: str) -> str:
    """What the text has where the reference has the term (for the report)."""
    ref, hyp, shown = tokens(reference), tokens(text), tokens(text, fold=False)
    want = tokens(term)
    start = _find(want, ref)
    if start < 0:
        return "?"
    end = start + len(want)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ref, hyp, autojunk=False).get_opcodes():
        if i2 <= start or i1 >= end:
            continue
        if op == "equal":
            lo, hi = max(i1, start), min(i2, end)
            out += shown[j1 + lo - i1: j1 + hi - i1]
        elif op == "replace":
            out += shown[j1:j2]
    return " ".join(out) or "(nothing)"


# ── Clips ────────────────────────────────────────────────────────────────────
def hints_for(item: dict, hints: dict) -> list:
    text = " ".join(tokens(item["reference"]))
    return [(t, s) for t, s in hints.items() if " ".join(tokens(t)) in text]


def instructions(voice: dict, said_as: list) -> str:
    out = (f"Voice: a physician dictating clinical notes into speech recognition software. "
           f"Accent: {voice['accent']}, natural and mild, never exaggerated. Pace: {sv.PACE[voice['pace']]}. "
           f"Read the text exactly as written, word for word, with a short pause between sentences. "
           f"Do not add, skip or change any word. Say medical terms, drug names and abbreviations as an "
           f"experienced clinician would.")
    if said_as:
        out += " Pronounce: " + "; ".join(f"{t} as {s}" for t, s in said_as) + "."
    return out


def plan(panel: dict, voices=None, items=None, set_path: Path = SET) -> list:
    hints, script_set = load_set(set_path)
    clips = []
    for v in panel["voices"]:
        if voices and v["id"] not in voices:
            continue
        for it in script_set:
            if items and it["id"] not in items:
                continue
            text = sv.voice_text(it["reference"], mode="natural")
            clips.append({"voice_id": v["id"], "voice": v["voice"], "accent": v["accent"], "item": it["id"],
                          "topic": it["topic"], "item_split": it["split"], "targets": it["targets"],
                          "input": text, "required": text, "instructions": instructions(v, hints_for(it, hints))})
    return clips


def manifest(out: Path) -> list:
    path = out / "manifest.jsonl"
    if not path.is_file():
        return []
    return [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r and (out / r["wav"]).is_file()]


def cmd_plan(args, panel):
    clips = plan(panel, args.voices, args.items)
    done = {(r["voice_id"], r["item"]) for r in manifest(args.out)}
    minutes, usd = sv.estimate(clips)
    print(f"{len(clips)} clips ({sum((c['voice_id'], c['item']) not in done for c in clips)} not made yet), "
          f"{sum(len(c['targets']) for c in clips)} terms, about {minutes:.0f} minutes of speech, about ${usd:.2f}")
    for c in clips[: args.show]:
        print(f"\n[{c['voice_id']} {c['voice']} / {c['item']}]\n{c['instructions']}\n{c['input']}")


def cmd_make(args, panel, post=None):
    post = post or sv._post
    if not args.go:
        raise SystemExit("make spends money: add --go (run 'plan' first to see the cost)")
    done = {(r["voice_id"], r["item"]) for r in manifest(args.out)}
    clips = [c for c in plan(panel, args.voices, args.items) if (c["voice_id"], c["item"]) not in done]
    minutes, usd = sv.estimate(clips)
    if usd > args.budget_usd:
        raise SystemExit(f"estimated ${usd:.2f} is over --budget-usd {args.budget_usd}")
    key = sv.read_key(args.key_file)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "README.txt").write_text(sv.README.format(model=panel["model"], terms=panel["terms_read"]),
                                         encoding="utf-8")
    lock, spent = threading.Lock(), {"seconds": 0.0, "clips": 0}

    def one(clip):
        if spent["seconds"] / 60 * sv.USD_PER_MINUTE > args.budget_usd:
            return
        pcm = np.frombuffer(sv.speak(clip, panel["model"], key, post), dtype="<i2").astype(np.float64)
        rel = Path(clip["voice_id"]) / f"{clip['item']}.wav"
        sv.write_wav(args.out / rel, sv.resample(pcm), sv.RATE)
        seconds = len(pcm) / sv.SOURCE_RATE
        row = dict(clip, wav=str(rel).replace("\\", "/"), seconds=round(seconds, 2), engine=panel["engine"],
                   model=panel["model"], rate=sv.RATE, ai_generated=True,
                   sha256=hashlib.sha256(pcm.astype("<i2").tobytes()).hexdigest(),
                   made=dt.datetime.now().isoformat(timespec="seconds"), terms_read=panel["terms_read"])
        with lock:
            with open(args.out / "manifest.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            spent["seconds"] += seconds
            spent["clips"] += 1
            print(f"{spent['clips']}/{len(clips)} {clip['voice_id']} {clip['item']} {seconds:.1f} s", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in [pool.submit(one, c) for c in clips]:
            future.result()
    print(f"made {spent['clips']} clips, {spent['seconds'] / 60:.1f} minutes, "
          f"about ${spent['seconds'] / 60 * sv.USD_PER_MINUTE:.2f}")


def read_audio(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768


# ── Check: can large-v3 hear each term when it is told the term? ─────────────
def cmd_check(args, panel):
    from fw_engine import register_cuda_dll_dirs
    register_cuda_dll_dirs()
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cuda", compute_type="float16")
    path = args.out / "check.jsonl"
    seen = set()
    if path.is_file():
        seen = {r["sha256"] for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r}
    rows = [r for r in manifest(args.out) if r["sha256"] not in seen]
    unclear = 0
    for n, r in enumerate(rows, 1):
        pad = np.zeros(sv.RATE, dtype=np.float32)
        audio = np.concatenate([pad, read_audio(args.out / r["wav"]), pad])
        prompt = "Vocabulary: " + ", ".join(r["targets"]) + "."
        segs, _ = model.transcribe(audio, language="en", beam_size=5, initial_prompt=prompt,
                                   condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segs)
        hits = {t: found(t, heard) for t in r["targets"]}
        gaps = sv.judge(r, heard)                 # lines the voice skipped or added
        unclear += sum(not h for h in hits.values())
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"voice_id": r["voice_id"], "item": r["item"], "sha256": r["sha256"],
                                "hits": hits, "gaps": gaps, "heard": heard}, ensure_ascii=False) + "\n")
        print(f"{n}/{len(rows)} {r['voice_id']} {r['item']}: {sum(hits.values())}/{len(hits)} heard primed"
              + (f"; voice gaps {gaps}" if gaps else ""), flush=True)
    print(f"checked {len(rows)} clips; {unclear} terms not heard even when primed (listen to these)")


# ── Run: decode as the app does ──────────────────────────────────────────────
def pin(spec: str) -> None:
    import psutil
    cpus = []
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        cpus += list(range(int(lo), int(hi or lo) + 1))
    psutil.Process().cpu_affinity(cpus)


def cmd_run(args, panel):
    if args.pin:
        pin(args.pin)
    if args.device:
        os.environ["MYTRANSCRIBE_DEVICE"] = args.device
    if args.threads:
        os.environ["MYTRANSCRIBE_CPU_THREADS"] = str(args.threads)
    out = args.out / "runs" / args.name
    out.mkdir(parents=True, exist_ok=True)
    # A new install: the bundled vocabulary and medications, none of this PC's own word fixes.
    os.environ["MYTRANSCRIBE_MEDICATIONS_FILE"] = str(out / "no_personal_medications.txt")
    os.environ["MYTRANSCRIBE_CORRECTIONS_FILE"] = str(out / "no_personal_corrections.txt")
    import dictation_reliability as dr
    import settings_suite
    from vocab import build_text_pipeline
    profile = settings_suite.PROFILES[PROFILE]
    path = out / "decodes.jsonl"
    done = set()
    if path.is_file():
        done = {r["sha256"] for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r}
    engine = dr.make_engine("whisper", args.model)
    style = dr.style_for(profile)
    (out / "run.json").write_text(json.dumps({
        "model": str(engine.config.model), "device": engine.config.device, "compute_type": engine.config.compute_type,
        "threads": engine.config.cpu_threads, "pin": args.pin, "profile": PROFILE,
        "personal_files": "none (a new install)", "started": dt.datetime.now().isoformat(timespec="seconds")},
        indent=1), encoding="utf-8")
    todo = [r for r in manifest(args.out) if r["sha256"] not in done]
    t0 = time.perf_counter()
    for n, r in enumerate(todo, 1):
        # A fresh pipeline per clip, as for a new dictation: results do not depend on clip order.
        builder, post = build_text_pipeline(style, count=getattr(engine, "count_tokens", None))
        audio = dr.load_wav(args.out / r["wav"])
        final, _pieces, elapsed, _rescued, raw = dr.run_pipeline(engine, audio, None, style, builder, post,
                                                                profile, with_spoken=True)
        hits = {t: found(t, final) for t in r["targets"]}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"voice_id": r["voice_id"], "item": r["item"], "sha256": r["sha256"], "final": final,
                                "raw": raw, "hits": hits, "elapsed_s": round(elapsed, 2),
                                "audio_s": round(len(audio) / sv.RATE, 2)}, ensure_ascii=False) + "\n")
        print(f"{args.name} {n}/{len(todo)} {r['voice_id']} {r['item']}: {sum(hits.values())}/{len(hits)} "
              f"in {elapsed:.1f}s (total {time.perf_counter() - t0:.0f}s)", flush=True)


# ── Report ───────────────────────────────────────────────────────────────────
def _rows(path: Path) -> dict:
    if not path.is_file():
        return {}
    return {r["sha256"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r}


def tally(items: list, clips: list, check: dict, runs: dict) -> list:
    """
    One row per term: how many clips count, how many each run got, what it wrote instead.

    A clip counts for a term once some decode wrote the term: the primed check or any run.
    That shows the voice said it recognisably. Where none did, the voice may have said it
    wrongly or skipped the line, so the clip goes on the list to listen to instead.
    Hits are worked out again from the saved text, so a corrected spelling list applies.
    """
    by_id = {it["id"]: it for it in items}
    table = {}
    for c in clips:
        it = by_id[c["item"]]
        chk = check.get(c["sha256"])
        decodes = {n: runs[n].get(c["sha256"]) for n in runs}
        for term in it["targets"]:
            row = table.setdefault((it["id"], term), {"item": it["id"], "topic": it["topic"], "split": it["split"],
                                                       "term": term, "counted": 0, "unclear": [],
                                                       **{n: 0 for n in runs}, **{n + "_as": [] for n in runs}})
            hits = {n: d is not None and written(it, term, d["final"]) for n, d in decodes.items()}
            if not ((chk is not None and written(it, term, chk["heard"])) or any(hits.values())):
                row["unclear"].append(c["voice_id"])
                continue
            row["counted"] += 1
            for name, d in decodes.items():
                if d is None:
                    continue
                if hits[name]:
                    row[name] += 1
                else:
                    row[name + "_as"].append(f"{c['voice_id']}: {heard_as(it['reference'], term, d['final'])}")
    return list(table.values())


def cmd_report(args, panel):
    _, items = load_set()
    clips = manifest(args.out)
    check = _rows(args.out / "check.jsonl")
    runs = {n: _rows(args.out / "runs" / n / "decodes.jsonl") for n in args.names}
    rows = tally(items, clips, check, runs)
    lines = [f"# Term benchmark ({dt.date.today().isoformat()})", "",
             f"{len(clips)} clips, {len(items)} items, voices {sorted({c['voice_id'] for c in clips})}.", ""]
    for split in ("all", "tune", "check"):
        part = [r for r in rows if split == "all" or r["split"] == split]
        counted = sum(r["counted"] for r in part)
        cells = [f"{n} {sum(r[n] for r in part)}/{counted} ({100 * sum(r[n] for r in part) / max(1, counted):.1f}%)"
                 for n in runs]
        lines.append(f"- {split}: " + "; ".join(cells) + f"; unclear (listen) {sum(len(r['unclear']) for r in part)}")
    for n in runs:
        missed = sorted((r for r in rows if r[n] < r["counted"]), key=lambda r: (r[n] - r["counted"], r["term"]))
        lines += ["", f"## Missed by {n} ({len(missed)} terms)", "",
                  "| term | topic | split | right | written instead |", "|---|---|---|---|---|"]
        for r in missed:
            lines.append(f"| {r['term']} | {r['topic']} | {r['split']} | {r[n]}/{r['counted']} | "
                         f"{'; '.join(r[n + '_as'])} |")
    unclear = [r for r in rows if r["unclear"]]
    lines += ["", f"## To listen to ({len(unclear)} terms): not written even by large-v3 told the term", ""]
    lines += [f"- {r['term']} ({r['item']}): {', '.join(r['unclear'])}" for r in unclear]
    report = args.out / "runs" / f"report_{'_'.join(args.names)}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out / "runs" / f"report_{'_'.join(args.names)}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False),
                                                                          encoding="utf-8")
    print("\n".join(lines[:8]))
    print(f"report: {report}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("plan", "make", "check", "run", "report"))
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--panel", type=Path, default=sv.PANEL)
    ap.add_argument("--key-file", type=Path, default=sv.KEY_FILE)
    ap.add_argument("--voices", type=lambda s: s.split(","))
    ap.add_argument("--items", type=lambda s: s.split(","))
    ap.add_argument("--go", action="store_true", help="make: actually call the API (costs money)")
    ap.add_argument("--budget-usd", type=float, default=3.0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--show", type=int, default=1)
    ap.add_argument("--model", help="check, run: Whisper model folder")
    ap.add_argument("--name", help="run: a name for this run's results")
    ap.add_argument("--device", choices=("cpu", "cuda"), help="run: force the device (default: as the app picks)")
    ap.add_argument("--threads", type=int, help="run: processor threads")
    ap.add_argument("--pin", help="run: logical CPUs to hold the process to, e.g. 16-19")
    ap.add_argument("--names", type=lambda s: s.split(","), default=["gpu", "cpu"], help="report: runs to compare")
    args = ap.parse_args(argv)
    panel = sv.load_panel(args.panel)
    {"plan": cmd_plan, "make": cmd_make, "check": cmd_check, "run": cmd_run, "report": cmd_report}[args.command](args, panel)


if __name__ == "__main__":
    main()
