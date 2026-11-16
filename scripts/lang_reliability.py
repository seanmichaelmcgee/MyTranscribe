"""
Dictated punctuation and commands in Spanish, French and Swahili, end to end.

There are no recordings of clinicians dictating in these languages, so this
builds the nearest thing that can be made offline: published sentences (the
FLEURS test transcripts, CC BY 4.0) and the draft reading sets, turned into
their dictated form ("... dolor torácico COMA sin disnea PUNTO NUEVO PÁRRAFO")
and read by open-source Piper voices. The audio goes through the app's
pipeline with the language set, and the result is compared with the original
punctuated text. A computer voice is not a person dictating: this is for
writing and regression-testing the language packs, not an accuracy claim.

    lang_reliability.py make  --language es --fleurs results_1060/fleurs --voices results_1060/piper_voices --out <dir>
    lang_reliability.py run   --language es --out <dir> --split dev [--profile candidate|classic] [--model <folder>]
    lang_reliability.py score --language es --out <dir> --split dev

Splits: dev (for writing rules), held (run once at the end), med (the draft
medical reading set, Spanish and French only). "make" needs the piper-tts
package; everything stays under the ignored results_1060/ tree.
"""

import argparse
import difflib
import json
import re
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import lang_commands  # noqa: E402
import lang_packs  # noqa: E402

FLEURS_NAME = {"es": "es_419", "fr": "fr_fr", "sw": "sw_ke"}
VOICES = {"es": ("es_ES-davefx-medium", "es_MX-claude-high"), "fr": ("fr_FR-siwis-medium", "fr_FR-upmc-medium"),
          "sw": ("sw_CD-lanfrica-medium",)}
SKIP_ROWS = 300            # the first 300 test rows are the recognition baseline: keep the text sets apart
ITEMS_PER_SPLIT = 20
_PLAIN = re.compile(r"^[^\W\d_][^\d_\"“”«»()\[\]/%&+=*#@<>|\\{}–—…!¿¡]*[.?]$", re.UNICODE)
_MARKS = ".,:;?"


def word_tokens(text: str) -> list:
    return re.findall(r"[^\W_]+(?:['’\-][^\W_]+)*", text.lower().replace("’", "'"), re.UNICODE)


def mark_tokens(text: str) -> list:
    """Words and punctuation marks as separate tokens; line breaks as one token each."""
    return re.findall(r"\n+|[^\W_]+(?:['’\-][^\W_]+)*|[.,:;?!«»\"()]", text.lower().replace("’", "'"), re.UNICODE)


def mark_errors(reference: str, hyp: str):
    """(marks in reference, missing, added) from a token alignment."""
    is_mark = lambda t: not t[0].isalnum() and not t.startswith("\n")      # noqa: E731
    r, h = mark_tokens(reference), mark_tokens(hyp)
    missing = added = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, r, h, autojunk=False).get_opcodes():
        if op != "equal":
            missing += sum(map(is_mark, r[i1:i2]))
            added += sum(map(is_mark, h[j1:j2]))
    return sum(map(is_mark, r)), missing, added


_RX_FR = {"mg": "milligrammes", "milligramme": "milligrammes", "g": "grammes", "gramme": "grammes",
          "µg": "microgrammes", "mcg": "microgrammes", "microgramme": "microgrammes", "ml": "millilitres",
          "millilitre": "millilitres", "kg": "kilogrammes", "h": "heures", "heure": "heures", "un": "1", "une": "1",
          "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9",
          "dix": "10", "pourcent": "pourcent", "comprimé": "comprimés", "comprimée": "comprimés",
          "comprimées": "comprimés", "gélule": "gélules", "goutte": "gouttes", "jour": "jours", "semaine": "semaines"}


def rx_tokens(text: str) -> list:
    """
    Word tokens for scoring French prescriptions against PxCorpus transcripts, which are
    unaccented, write "1" for "un" and spell units out. Units, small numbers, plural of
    the commonest nouns, accents, hyphens, "%" and the filler "euh" are made the same on
    both sides; drug names and everything else are compared as written.
    """
    import unicodedata
    text = text.lower().replace("’", "'").replace("%", " pourcent ").replace("pour cent", "pourcent")
    text = re.sub(r"(\d)\s*h\b", r"\1 heures", text)
    text = re.sub(r"(?<=\d)[ .](?=\d{3}\b)", "", text)                     # 1 000 / 1.000 -> 1000
    out = []
    for w in re.findall(r"[^\W_]+(?:'[^\W_]+)*", text.replace("-", " "), re.UNICODE):
        w = _RX_FR.get(w, w)
        w = "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn")
        if w not in ("euh", "heu"):
            out.append(w)
    return out


def edit_distance(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[len(b)]


def layout(text: str) -> list:
    return re.findall(r"\n\n+|\n|[\"«»]", re.sub(r"[ \t]+\n", "\n", text.strip()))


def voiced_text(reference: str, pack) -> str:
    """What the voice is given: the dictated words, each followed by its mark so the voice pauses."""
    say, text = pack.say, reference
    text = re.sub(r"(\d)/(\d)", rf"\1 {pack.over[0]} \2", text)
    left, right = (re.escape(q.strip()) for q in pack.quotes)
    text = re.sub(left + r"\s*([^\n]*?)\s*" + right, lambda m: f" {say['open']}, {m.group(1)}, {say['close']}", text)
    titles = "".join(rf"(?<!\b{t})" for t in pack.titles)
    text = re.sub(r"[ \t]*" + titles + r"([.,:;?])(?=\s|$)", lambda m: f" {say[m.group(1)]}{m.group(1)}", text)
    text = re.sub(r"[ \t]*\n[ \t]*\n[ \t]*", f" {say[chr(10) * 2]}. ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", f" {say[chr(10)]}. ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


# ── make ─────────────────────────────────────────────────────────────────────
def fleurs_sentences(folder: Path) -> list:
    seen, out = set(), []
    rows = (folder / "test.tsv").read_text(encoding="utf-8").splitlines()
    for line in rows[SKIP_ROWS:]:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        text = " ".join(parts[2].split())
        if text in seen or not _PLAIN.match(text) or not 8 <= len(text.split()) <= 28:
            continue
        seen.add(text)
        out.append(text)
    return out


def cmd_make(args):
    import validation_tool as vt
    pack = lang_packs.get(args.language)
    sentences = fleurs_sentences(args.fleurs / FLEURS_NAME[args.language])
    cells = []
    for split, base in (("dev", 0), ("held", 3 * ITEMS_PER_SPLIT)):
        for i in range(ITEMS_PER_SPLIT):
            three = sentences[base + 3 * i: base + 3 * i + 3]
            if len(three) < 3:
                break
            joiner = "\n\n" if i % 2 == 0 else "\n"       # a paragraph in half the items, a line break in the rest
            cells.append({"id": f"{split}{i:02d}", "split": split,
                          "reference": f"{three[0]} {three[1]}{joiner}{three[2]}"})
    med = ROOT / "validation" / f"validation_set_{args.language}_v1.txt"
    if med.is_file():
        cells += [{"id": it["id"], "split": "med", "reference": it["reference"]} for it in vt.load_set(med)]
    args.out.mkdir(parents=True, exist_ok=True)

    from piper import PiperVoice
    made = 0
    for v, name in enumerate(VOICES[args.language]):
        voice = PiperVoice.load(str(args.voices / f"{name}.onnx"))
        for c in cells:
            wav = args.out / f"{c['id']}__v{v}.wav"
            if not wav.is_file():
                with wave.open(str(wav), "wb") as w:
                    voice.synthesize_wav(voiced_text(c["reference"], pack), w)
                made += 1
    table = [dict(c, voice=v, wav=f"{c['id']}__v{v}.wav", spoken=vt.spoken_form(c["reference"], language=args.language))
             for v in range(len(VOICES[args.language])) for c in cells]
    (args.out / "cells.json").write_text(json.dumps(table, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{args.language}: {len(table)} cells ({len(cells)} texts x {len(VOICES[args.language])} voices), {made} synthesised")


# ── run ──────────────────────────────────────────────────────────────────────
def cmd_run(args):
    import dictation_reliability as dr
    import engines
    import pause_flow
    from faster_whisper import decode_audio

    pack = lang_packs.get(args.language)
    model = args.model or engines.tuned_model(args.language)
    engine = dr.make_engine("whisper", str(model) if model else None)
    engine.language = pack.code
    pause_flow.set_language(pack)
    profile = dr.PROFILES["candidate" if args.profile == "candidate" else "baseline"]
    post = lang_commands.corrector_for(pack)
    if post is not None:
        post.same_sound = True                             # as with Extra corrections on
    import os
    prompt = os.environ.get("LANG_PROMPT", lang_commands.prompt_for(pack, True))   # trial: another prompt
    cells = [c for c in json.loads((args.out / "cells.json").read_text(encoding="utf-8")) if c["split"] == args.split]
    for c in cells:
        audio = decode_audio(str(args.out / c["wav"]), sampling_rate=16000)
        c["raw"] = dr.run_pipeline(engine, audio, None, prompt, None, post, profile, with_spoken=True)[4]
    out = args.out / f"raw_{args.split}_{args.profile}.json"
    out.write_text(json.dumps(cells, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{args.language} {args.split} {args.profile}: {len(cells)} cells transcribed "
          f"(model {Path(str(engine.config.model)).name})")


# ── score ────────────────────────────────────────────────────────────────────
def score_cells(cells: list, pack, punctuation: bool) -> dict:
    left_re = lang_commands._any(list(pack.marks) + list(pack.paragraph) + list(pack.line)
                                 + list(pack.open_quote) + list(pack.close_quote))
    n = miss = add = left = errs = words = ok = 0
    for c in cells:
        text = lang_commands.apply(lang_commands.format_readings(c["raw"], pack), pack, punctuation=punctuation)
        a, b, d = mark_errors(c["reference"], text)
        n, miss, add = n + a, miss + b, add + d
        left += len(left_re.findall(text))
        ref, hyp = word_tokens(c["reference"]), word_tokens(text)
        errs += edit_distance(ref, hyp)
        words += len(ref)
        ok += layout(c["reference"]) == layout(text)
        c["text"] = text
    return {"cells": len(cells), "marks": n, "marks_missing": miss, "marks_added": add, "command_words_left": left,
            "wer": round(100 * errs / max(1, words), 2), "layout_ok": ok}


def cmd_score(args):
    pack = lang_packs.get(args.language)
    path = args.out / f"raw_{args.split}_{args.profile}.json"
    cells = json.loads(path.read_text(encoding="utf-8"))
    print(f"{args.language} {args.split} {args.profile}: {len(cells)} cells")
    for label, on in (("marks off", False), ("marks on", True)):
        s = score_cells(cells, pack, on)
        print(f"  {label:10s} marks missing {s['marks_missing']}/{s['marks']}, added {s['marks_added']}; "
              f"command words left {s['command_words_left']}; WER {s['wer']:.2f}%; layout ok {s['layout_ok']}/{s['cells']}")
        if on and args.show:
            for c in cells[:args.show]:
                print("---", c["id"], c["voice"], "\nRAW:", c["raw"], "\nOUT:", c["text"])


# ── files: real recordings with a reference text ─────────────────────────────
def cmd_files(args):
    """Run a folder of recordings (refs.json: [{id, wav, reference}]) through the pipeline and score words."""
    import dictation_reliability as dr
    import engines
    import pause_flow
    from faster_whisper import decode_audio

    pack = lang_packs.get(args.language)
    name = "dictated" if args.dictated else "plain"
    saved = args.out / f"out_{name}.json"
    if args.rescore:
        rows = json.loads(saved.read_text(encoding="utf-8"))
    else:
        model = args.model or engines.tuned_model(args.language)
        engine = dr.make_engine("whisper", str(model) if model else None)
        engine.language = pack.code
        pause_flow.set_language(pack)
        post = lang_commands.corrector_for(pack)
        if post is not None:
            post.same_sound = True
        rows = json.loads((args.out / "refs.json").read_text(encoding="utf-8"))
        import os
        prompt = os.environ.get("LANG_PROMPT", lang_commands.prompt_for(pack, args.dictated))
        for r in rows:
            audio = decode_audio(str(args.out / r["wav"]), sampling_rate=16000)
            r["raw"] = dr.run_pipeline(engine, audio, None, prompt, None, post, dr.PROFILES["candidate"],
                                       with_spoken=True)[4]
    for r in rows:
        r["text"] = lang_commands.apply(lang_commands.format_readings(r["raw"], pack), pack, punctuation=args.dictated)
    saved.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    tokens = rx_tokens if args.prescriptions else word_tokens
    for label, key in (("before conversion", "raw"), ("final text", "text")):
        errs = sum(edit_distance(tokens(r["reference"]), tokens(r[key])) for r in rows)
        words = sum(len(tokens(r["reference"])) for r in rows)
        print(f"{args.language} {args.out.name} ({name}) {label}: {len(rows)} recordings, {words} words, "
              f"WER {100 * errs / max(1, words):.2f}%")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, func in (("make", cmd_make), ("run", cmd_run), ("score", cmd_score), ("files", cmd_files)):
        p = sub.add_parser(name)
        p.add_argument("--language", required=True, choices=sorted(lang_packs.PACKS))
        p.add_argument("--out", required=True, type=Path)
        p.set_defaults(func=func)
        if name == "files":
            p.add_argument("--model")
            p.add_argument("--dictated", action="store_true", help="the speakers dictate punctuation")
            p.add_argument("--prescriptions", action="store_true",
                           help="score with the French prescription normaliser (PxCorpus transcripts)")
            p.add_argument("--rescore", action="store_true", help="score the saved output again; no recognition")
            continue
        if name == "make":
            p.add_argument("--fleurs", required=True, type=Path)
            p.add_argument("--voices", required=True, type=Path)
        else:
            p.add_argument("--split", default="dev", choices=["dev", "held", "med"])
            p.add_argument("--profile", default="candidate", choices=["candidate", "classic"])
        if name == "run":
            p.add_argument("--model")
        if name == "score":
            p.add_argument("--show", type=int, default=0)
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
