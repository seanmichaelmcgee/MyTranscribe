"""
Synthetic test set for spoken punctuation ("period", "comma", "colon" ...).

The owner's recordings contain almost no dictated punctuation marks, so this
reads the corpus scripts aloud with the marks spoken, using the two Windows
text-to-speech voices, and runs the result through the app pipeline. It shows
how the model writes a spoken mark and whether voice_commands turns it back
into the mark. A computer voice is not a person dictating: use it to develop
and regression-test the rules, not as an accuracy claim.

    spoken_punctuation_tts.py make  --corpus-root results_1060 --out <dir> --split dev
    spoken_punctuation_tts.py run   --out <dir> --split dev [--model <folder>]
    spoken_punctuation_tts.py score --out <dir> --split dev

"run" saves the text before command conversion, so "score" (no GPU) can be
repeated while the rules change. Everything stays under the ignored
results_1060/ tree.
"""

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

VOICES = ("Microsoft David Desktop", "Microsoft Zira Desktop")
MARK_WORDS = {".": "period", ",": "comma", ":": "colon", ";": "semicolon", "?": "question mark"}
_COMMAND = re.compile(r"^(?:(?:new|next) (?:line|paragraph)|(?:open|close|end) quotes?|unquote|\w+ period)$", re.I)
_SEGMENT = re.compile(r"(.*?)([.,:;?])(?=\s|$)", re.S)
_LEFTOVER = re.compile(r"\b(?:period|full stop|comma|colon|semicolon|question mark)\b", re.I)
_PS = r"""
Add-Type -AssemblyName System.Speech
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, 'Sixteen', 'Mono')
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
foreach ($j in (Get-Content -Raw -Encoding UTF8 $args[0] | ConvertFrom-Json)) {
    $s.SelectVoice($j.voice); $s.SetOutputToWaveFile($j.out, $fmt); $s.Speak($j.text)
}
$s.SetOutputToNull(); $s.Dispose()
"""


def speak_marks(spoken: str) -> str:
    """The read-aloud script with each punctuation mark also said as a word."""
    out, pos = [], 0
    for m in _SEGMENT.finditer(spoken):
        body, mark = m.group(1), m.group(2)
        if _COMMAND.match(body.strip()):
            out.append(f"{body}{mark}")                   # "New line." is already a command
        else:
            out.append(f"{body} {MARK_WORDS[mark]}{mark}")  # keep the mark for the voice's pause
        pos = m.end()
    return "".join(out) + spoken[pos:]


def tokens(text: str):
    """Lower-case words, with punctuation marks and line breaks as their own tokens."""
    return re.findall(r"\n+|[A-Za-z0-9]+(?:['’\-.][A-Za-z0-9]+)*|[.,:;?!()\"]", text.lower())


def mark_errors(reference: str, hyp: str):
    """(marks in reference, marks missing, marks added) from a token alignment."""
    is_mark = lambda t: not t[0].isalnum() and not t.startswith("\n")   # noqa: E731
    r, h = tokens(reference), tokens(hyp)
    missing = added = 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, r, h, autojunk=False).get_opcodes():
        if op != "equal":
            missing += sum(map(is_mark, r[i1:i2]))
            added += sum(map(is_mark, h[j1:j2]))
    return sum(map(is_mark, r)), missing, added


def cmd_make(args):
    import dictation_reliability as dr

    args.out.mkdir(parents=True, exist_ok=True)
    cells, jobs = [], []
    for e in dr.load_corpus(args.corpus_root, args.split):
        text = speak_marks(e["spoken"])
        if text == e["spoken"]:
            continue
        for v, voice in enumerate(VOICES):
            wav = args.out / f"{e['id']}__v{v}.wav"
            cells.append({"id": e["id"], "voice": v, "wav": wav.name, "said": text, "reference": e["reference"]})
            if not wav.is_file():
                jobs.append({"out": str(wav.resolve()), "text": text, "voice": voice})
    (args.out / f"cells_{args.split}.json").write_text(json.dumps(cells, indent=1, ensure_ascii=False), encoding="utf-8")
    if jobs:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
            (Path(tmp) / "tts.ps1").write_text(_PS, encoding="utf-8")
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                            str(Path(tmp) / "tts.ps1"), str(Path(tmp) / "jobs.json")], check=True)
    print(f"{len(cells)} cells, {len(jobs)} synthesised")


def cmd_run(args):
    import corti_benchmark as cb
    import dictation_reliability as dr

    profile = dr.PROFILES["candidate"]
    dr.register_cuda_dll_dirs()
    cfg = dr.choose_config(dr.detect_hardware(), accurate=True)
    if args.model:
        cfg.model = args.model
    engine = dr.FasterWhisperEngine(cfg)
    engine.warmup()
    style = dr.load_prompt()
    builder, post = dr.build_text_pipeline(style, count=engine.count_tokens, env={})
    cells = json.loads((args.out / f"cells_{args.split}.json").read_text(encoding="utf-8"))
    for c in cells:
        audio = cb.load_wav(args.out / c["wav"])
        c["raw"] = dr.run_pipeline(engine, audio, None, style, builder, post, profile, with_spoken=True)[4]
    (args.out / f"raw_{args.split}.json").write_text(json.dumps(cells, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{len(cells)} cells transcribed")


def cmd_score(args):
    import dictation_reliability as dr
    import voice_commands

    cells = json.loads((args.out / f"raw_{args.split}.json").read_text(encoding="utf-8"))
    print(f"{len(cells)} cells ({args.split})")
    for label, kwargs in (("marks off", {"lenient": True}), ("marks on", {"lenient": True, "punctuation": True})):
        n = miss = add = left = errs = words = fmt = 0
        for c in cells:
            text = voice_commands.apply(c["raw"], **kwargs)
            a, b, d = mark_errors(c["reference"], text)
            n, miss, add = n + a, miss + b, add + d
            left += len(_LEFTOVER.findall(text))
            errs += dr.word_edits(c["reference"], text)
            words += len(dr._tokens(c["reference"]))
            fmt += dr.structure(c["reference"]) == dr.structure(text)
            if args.show and label == "marks on":
                print("---", c["id"][:30], c["voice"], "\n", text)
        print(f"{label:10s} marks missing {miss}/{n}, added {add}; mark words left {left}; "
              f"WER {100 * errs / words:.2f}%; layout ok {fmt}/{len(cells)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, func in (("make", cmd_make), ("run", cmd_run), ("score", cmd_score)):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True, type=Path)
        p.add_argument("--split", default="dev", choices=["dev", "held"])
        p.set_defaults(func=func)
        if name == "make":
            p.add_argument("--corpus-root", required=True, type=Path)
        if name == "run":
            p.add_argument("--model")
        if name == "score":
            p.add_argument("--show", action="store_true")
    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
