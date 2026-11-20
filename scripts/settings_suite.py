"""
settings_suite.py — milestone 1 of the settings suite: the baseline.

Plays every synthetic clip (results_1060/synthetic_voices/en_v1) through the app's own
pipeline under each setup-wizard answer and scores the result. Mission and plan:
docs/settings/SETTINGS_SUITE.md.

    settings_suite.py run    --name baseline [--voices V01] [--items e01,n02] [--model <folder>]
    settings_suite.py report --name baseline

"run" decodes each clip once per decode group (the prompt differs when spoken punctuation
is on) and saves the raw text, so "report" and new text-only profiles need no graphics
card. Everything is local; results go under the ignored results_1060/settings_suite/.
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import synth_voices as sv  # noqa: E402
from tuning import sets  # noqa: E402
from tuning.score import clinical_errors  # noqa: E402

AUDIO = ROOT / "results_1060" / "synthetic_voices" / "en_v1"
OUT = ROOT / "results_1060" / "settings_suite"
SR = 16000

_CORE = {"transcriber": {"pause_aware": True, "post_roll_s": 0.3}, "extra_fixes": True}
# One profile per answer to "How do you dictate punctuation?" (src/setup_wizard.py), as
# the app sets it. "talk" is also what a new install gets without the wizard.
PROFILES = {
    "every": dict(_CORE, group="marks", commands={"lenient": True, "punctuation": True, "only_dictated_commas": True}),
    "some": dict(_CORE, group="marks", commands={"lenient": True, "punctuation": True}),
    "talk": dict(_CORE, group="plain", commands={"lenient": True}),
    # "talk" with the layout commands in the style prompt: tried 2026-11-18, not adopted
    # (no gain on the owner's real recordings). Decoded only when asked for (--groups layout).
    "talk_layout": dict(_CORE, group="layout", layout_prompt=True, commands={"lenient": True}),
}
DEFAULT = "talk"
# What setup gives each speaker style. Since 2026-11-18 the natural-speech answer also turns
# spoken punctuation on, so it is the "some" profile; "talk" is what natural speech got before
# (and what a new install keeps if setup is closed).
MATCH = {"every": "every", "sentence": "some", "layout": "some", "natural": "some", "notes": "some"}
_TITLE_NAME = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr)\. ((?:[A-Z][\w'-]+ ?)+)")
_SIGN_OFF = re.compile(r"\b(kind regards|yours sincerely|thank you)\b")


# ── What each clip should say ────────────────────────────────────────────────
def reference_for(item: dict, fidelity_row) -> str:
    """
    The item's written text, adjusted for a clip the check found incomplete: a missing
    sign-off is dropped from the reference (docs/testing/SYNTHETIC_VOICES.md); any other
    gap leaves the clip out (None).
    """
    ref = item["reference"]
    if not fidelity_row or not fidelity_row.get("flagged"):
        return ref
    said = " ".join(s for s, _ in fidelity_row["gaps"])
    if "doctor" not in said or any(h for _, h in fidelity_row["gaps"]):
        return None
    paragraphs = ref.split("\n\n")
    if _SIGN_OFF.search(said):
        return "\n\n".join(paragraphs[:-1])          # the whole "Kind regards,\nDr. X" paragraph
    lines = ref.split("\n")
    return "\n".join(lines[:-1])                     # only the name line


def names_in(text: str) -> list:
    return [m.group(1).strip() for m in _TITLE_NAME.finditer(text)]


def clips(voices=None, items=None) -> list:
    rows = [json.loads(x) for x in (AUDIO / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    fid = {}
    fpath = AUDIO / "fidelity.jsonl"
    if fpath.is_file():
        fid = {r["sha256"]: r for r in map(json.loads, fpath.read_text(encoding="utf-8").splitlines()) if r}
    by_id = {it["id"]: it for it in sets.load_set(ROOT / "validation" / sv.load_panel()["set"])}
    out = []
    for r in rows:
        if (voices and r["voice_id"] not in voices) or (items and r["item"] not in items):
            continue
        ref = reference_for(by_id[r["item"]], fid.get(r["sha256"]))
        if ref is None:
            continue
        out.append(dict(r, reference=ref, names=names_in(by_id[r["item"]]["reference"])))
    return sorted(out, key=lambda c: (c["voice_id"], c["item"]))


# ── Run ──────────────────────────────────────────────────────────────────────
def cmd_run(args):
    import dictation_reliability as dr
    from vocab import build_text_pipeline
    todo = clips(args.voices, args.items)
    out = OUT / args.name
    out.mkdir(parents=True, exist_ok=True)
    # A new install: the bundled vocabulary only, none of this PC's personal medications
    # or word fixes (those files are pointed at places that do not exist).
    os.environ["MYTRANSCRIBE_MEDICATIONS_FILE"] = str(out / "no_personal_medications.txt")
    os.environ["MYTRANSCRIBE_CORRECTIONS_FILE"] = str(out / "no_personal_corrections.txt")
    path = out / "decodes.jsonl"
    done = set()
    if path.is_file():
        done = {(r["voice_id"], r["item"], r["group"]) for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}
    engine = dr.make_engine("whisper", args.model or os.environ.get("MYTRANSCRIBE_MODEL"))
    groups = {p["group"]: p for p in PROFILES.values()}             # one representative per decode group
    if args.groups:
        groups = {g: p for g, p in groups.items() if g in args.groups}
    t0 = time.perf_counter()
    for group, profile in groups.items():
        style = dr.style_for(profile)
        builder, post = build_text_pipeline(style, count=getattr(engine, "count_tokens", None),
                                            classical=dr.classical_terms.on_for(engine))
        for n, c in enumerate(todo, 1):
            if (c["voice_id"], c["item"], group) in done:
                continue
            audio = dr.load_wav(AUDIO / c["wav"])
            _final, pieces, elapsed, rescued, raw = dr.run_pipeline(engine, audio, None, style, builder, post,
                                                                    profile, with_spoken=True)
            row = {"voice_id": c["voice_id"], "item": c["item"], "group": group, "raw": raw,
                   "elapsed_s": round(elapsed, 2), "audio_s": round(len(audio) / SR, 2), "rescued": rescued}
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"{group} {n}/{len(todo)} {c['voice_id']} {c['item']} {elapsed:.1f}s "
                  f"(total {time.perf_counter() - t0:.0f}s)", flush=True)
    (out / "run.json").write_text(json.dumps({"model": str(engine.config.model), "device": engine.config.device,
                                              "compute_type": engine.config.compute_type, "profiles": PROFILES,
                                              "personal_files": "none (a new install)"}, indent=1),
                                  encoding="utf-8")


# ── Score ────────────────────────────────────────────────────────────────────
def final_text(raw: str, profile: dict) -> str:
    """The text the app would copy, from the raw decode, for a text-only profile."""
    import text_fixes
    import voice_commands
    text = text_fixes.finish(raw, bool(profile.get("extra_fixes")))
    return voice_commands.apply(text, **profile.get("commands", {}))


def score(c: dict, text: str, is_medical, zipf) -> dict:
    import dictation_reliability as dr
    from eval_metrics import breakdown, normalize_words
    b = breakdown(c["reference"], text, names=c["names"], is_medical=is_medical, zipf=zipf)
    missing, extra = dr.sentence_end_errors(c["reference"], text)
    expected, found, added = dr.command_hits(c["reference"], text)
    clin = clinical_errors(c["reference"], text, is_medical)
    return {"words": len(normalize_words(c["reference"])), "errors": dr.word_edits(c["reference"], text),
            "errors_no_names": b.errors, "words_no_names": b.words,
            "format_ok": dr.format_ok(c["reference"], text), "uses_format": bool(dr.structure(c["reference"])),
            "breaks": [expected, found, added], "sent_missing": missing, "sent_extra": extra,
            "leftover_commands": len(dr._COMMAND_RE.findall(text)) + len(re.findall(
                r"\b(?:period|full stop|comma|semicolon)\b", text, re.I)),
            **clin}


def scored_rows(name: str) -> list:
    from wordfreq import zipf_frequency
    import vocab as vocab_mod
    from eval_metrics import load_medical_words
    zipf = lambda w: zipf_frequency(w, "en")                          # noqa: E731
    medical = load_medical_words(list(vocab_mod.DEFAULT_LEXICON_FILES) + list(vocab_mod.CORRECTION_ONLY_FILES),
                                 zipf=zipf)
    is_medical = lambda w: w in medical                               # noqa: E731
    decodes = {}
    for r in map(json.loads, (OUT / name / "decodes.jsonl").read_text(encoding="utf-8").splitlines()):
        decodes[(r["voice_id"], r["item"], r["group"])] = r
    panel = {v["id"]: v for v in sv.load_panel()["voices"]}
    rows = []
    for c in clips():
        for pname, profile in PROFILES.items():
            d = decodes.get((c["voice_id"], c["item"], profile["group"]))
            if d is None:
                continue
            text = final_text(d["raw"], profile)
            rows.append({"voice_id": c["voice_id"], "accent": panel[c["voice_id"]]["accent"],
                         "voice_split": panel[c["voice_id"]]["split"], "item": c["item"], "style": c["style"],
                         "item_split": c["item_split"], "profile": pname, "matched": MATCH[c["style"]] == pname,
                         "text": text, "elapsed_s": d["elapsed_s"], "audio_s": d["audio_s"],
                         **score(c, text, is_medical, zipf)})
    return rows


def pct(rows, num="errors", den="words") -> float:
    return 100 * sum(r[num] for r in rows) / max(1, sum(r[den] for r in rows))


def cmd_report(args):
    rows = scored_rows(args.name)
    out = OUT / args.name
    (out / "scored.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                      encoding="utf-8")
    dev = [r for r in rows if r["voice_split"] == "dev"]
    styles, profiles = list(MATCH), [p for p in PROFILES if any(r["profile"] == p for r in rows)]
    lines = ["Settings suite baseline (dev voices; held voices V06, V12 not shown)", "",
             "Word errors % by speaker style (rows) and wizard answer (columns); * = the matching answer", "",
             "| style | " + " | ".join(profiles) + " | best |", "|---|" + "---|" * (len(profiles) + 1)]
    for s in styles:
        rates = {p: pct([r for r in dev if r["style"] == s and r["profile"] == p]) for p in profiles}
        # Ties go to the matching answer, then the default ("defaults win ties").
        best = min(profiles, key=lambda p: (round(rates[p], 2), p != MATCH[s], p != DEFAULT))
        cells = [f"{rates[p]:.2f}{'*' if MATCH[s] == p else ''}" for p in profiles]
        lines.append(f"| {s} | " + " | ".join(cells) + f" | {best} |")
    matched = [r for r in dev if r["matched"]]
    lines += ["", "With the matching answer, by voice:", "",
              "| voice | accent | WER % | names free % | numbers | negations | medical | layout ok |",
              "|---|---|---|---|---|---|---|---|"]
    for vid in sorted({r["voice_id"] for r in rows}):
        sel = [r for r in rows if r["voice_id"] == vid and r["matched"]]
        fmt = [r for r in sel if r["uses_format"]]
        lines.append(f"| {vid}{' (held)' if sel and sel[0]['voice_split'] == 'held' else ''} | {sel[0]['accent']} "
                     f"| {pct(sel):.2f} | {pct(sel, 'errors_no_names', 'words_no_names'):.2f} "
                     f"| {sum(r['numbers'] for r in sel)}/{sum(r['numbers_of'] for r in sel)} "
                     f"| {sum(r['negations'] for r in sel)}/{sum(r['negations_of'] for r in sel)} "
                     f"| {sum(r['medical'] for r in sel)}/{sum(r['medical_of'] for r in sel)} "
                     f"| {sum(r['format_ok'] for r in fmt)}/{len(fmt)} |")
    lines += ["", f"All dev voices, matching answer: {pct(matched):.2f}% word errors "
              f"({pct(matched, 'errors_no_names', 'words_no_names'):.2f}% with names free); "
              f"default answer ('{DEFAULT}') for everyone: {pct([r for r in dev if r['profile'] == DEFAULT]):.2f}%."]
    secs = sum(r["elapsed_s"] for r in rows if r["profile"] in ("every", "talk"))
    audio = sum(r["audio_s"] for r in rows if r["profile"] in ("every", "talk"))
    lines.append(f"Decoding: {secs / 60:.1f} min for {audio / 60:.1f} min of audio ({audio / max(secs, 1):.1f}x real time).")
    text = "\n".join(lines)
    (out / "report.md").write_text(text + "\n", encoding="utf-8")
    print(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("run", "report"))
    ap.add_argument("--name", default="baseline")
    ap.add_argument("--voices", type=lambda s: s.split(","))
    ap.add_argument("--items", type=lambda s: s.split(","))
    ap.add_argument("--groups", type=lambda s: s.split(","), help="decode groups to run (default: all)")
    ap.add_argument("--model")
    args = ap.parse_args(argv)
    {"run": cmd_run, "report": cmd_report}[args.command](args)


if __name__ == "__main__":
    main()
