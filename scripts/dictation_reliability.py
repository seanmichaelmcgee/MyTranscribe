"""
dictation_reliability.py — do thinking pauses, spoken commands and Stop behave?

Runs fictional practice recordings through the SAME pipeline as the app
(ChunkedTranscriber -> prompts -> corrections -> voice_commands) under
conditions built from each original recording:

  orig        the recording as captured
  pause1.5    1.5 s thinking pauses spliced in mid-clause (room tone, not zeros)
  pause4      4 s thinking pauses at the same places
  cmdpause    2 s pauses before and after every spoken command
  tailpause   3 s pause before the last two words, then the recording ends
  earlystop   Stop arrives 0.15 s BEFORE the last word finishes (hold-to-talk
              released a touch early); the microphone keeps delivering audio

and reports, per condition:

  WER %       script-relative word error rate (names/punctuation ignored)
  breaks      sentence ends added at pause sites where the original had none
              (". Capital" in the middle of a clause: the meaning-changing case)
  drift       words that differ from the same pipeline's output on `orig`
  format      recordings whose line breaks / quotes / list numbers match the
              reference and contain no leftover command words
  tail        recordings whose last three reference words are in the output
  s-miss/s-extra  sentence ends missing / added against the reference
  commands    spoken formatting commands that reached the text (and extra ones)
  rescued     commands the pause-aware pipeline put back; secs = compute time

Pause positions come from one word-timestamp pass of the same local model and
are cached next to the results, so every pipeline setting sees identical audio.
Everything is local: no network, no API. Audio and text stay in --out (keep it
in an ignored folder; the corpus is private even though it is fictional).

  python scripts/dictation_reliability.py --corpus-root results_1060 --out results_1060/reliability/base
  python scripts/dictation_reliability.py ... --profile candidate --split dev

Opt-in tool: it changes no app default. --profile selects named pipeline
settings from PROFILES below ("baseline" = the app's defaults at the time).
"""

import argparse
import hashlib
import json
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bench_engine import load_wav                                       # noqa: E402
import chunked_transcriber as ct                                        # noqa: E402
from chunked_transcriber import ChunkedTranscriber                      # noqa: E402
from eval_metrics import align, normalize_words                         # noqa: E402
import fw_engine                                                        # noqa: E402
from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs       # noqa: E402
from hw_profile import choose_config, detect_hardware                   # noqa: E402
from prompt_loader import load_prompt                                   # noqa: E402
from vocab import build_text_pipeline                                   # noqa: E402
import text_fixes                                                       # noqa: E402
import voice_commands                                                   # noqa: E402

SR = 16000
CONDITIONS = ("orig", "pause1.5", "pause4", "cmdpause", "tailpause", "earlystop")
# Headset-only personal corpus (relative to --corpus-root) -> split. Recordings are
# correlated within a session, so whole sessions go to one split; real_headset
# alternates by index. "held" is only for the final check of a tuned candidate.
MANIFESTS = (
    ("real_headset/manifest.json", "alternate"),
    ("personal_curriculum/capture/lesson02/manifest.json", "dev"),
    ("personal_curriculum/lessons/04/captures/manifest.json", "dev"),
    ("personal_curriculum/capture/lesson01/manifest.json", "held"),
    ("personal_curriculum/capture/lesson02_retake/manifest.json", "held"),
    ("personal_curriculum/lessons/03/captures/manifest.json", "held"),
)
# Named pipeline settings. Keys: engine (FasterWhisperEngine attributes),
# transcriber (ChunkedTranscriber kwargs), commands (voice_commands.apply kwargs).
_CANDIDATE = {"transcriber": {"pause_aware": True, "post_roll_s": 0.3}, "commands": {"lenient": True}}
PROFILES = {
    "baseline": {},
    # What Options -> "Pause-aware dictation" switches on.
    "candidate": _CANDIDATE,
    # ... plus Options -> "Spoken punctuation".
    "candidate_marks": dict(_CANDIDATE, commands={"lenient": True, "punctuation": True}),
    # ... plus Options -> "Extra corrections".
    "candidate_full": dict(_CANDIDATE, commands={"lenient": True, "punctuation": True}, extra_fixes=True),
    # The text options without the pause-aware pipeline (for engines it does not suit).
    "classic_full": {"commands": {"lenient": True, "punctuation": True}, "extra_fixes": True},
    # Silence-handling variants tried on top of it (none was better; see the results note).
    "cand_pad150": dict(_CANDIDATE, engine={"decode_overrides": {"vad_parameters": {
        "min_silence_duration_ms": 700, "speech_pad_ms": 150}}}),
    "cand_pad100": dict(_CANDIDATE, engine={"decode_overrides": {"vad_parameters": {
        "min_silence_duration_ms": 700, "speech_pad_ms": 100}}}),
    "cand_vadoff": dict(_CANDIDATE, engine={"decode_overrides": {"vad_filter": False}}),
}
_COMMAND_WORDS = {"new", "next", "line", "paragraph", "open", "close", "end", "quote", "quotes",
                  "unquote", "period", "periods", "number"}
_COMMAND_RE = re.compile(r"\b(?:new|next)\s+(?:line|paragraph)\b|\b(?:open|close|end)\s+quotes?\b|\bunquote\b"
                         r"|\b(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s+periods?\b", re.I)
_TERMINAL = ".?!"


# ── Corpus ───────────────────────────────────────────────────────────────────
def load_corpus(root: Path, split: str):
    out = []
    for rel, rule in MANIFESTS:
        path = root / rel
        if not path.is_file():
            print(f"missing manifest (skipped): {rel}", file=sys.stderr)
            continue
        for i, e in enumerate(json.loads(path.read_text(encoding="utf-8"))):
            s = rule if rule != "alternate" else ("dev" if i % 2 == 0 else "held")
            if split not in ("all", s):
                continue
            wav = path.parent / e["audio"]
            if not wav.is_file():
                print(f"missing audio (skipped): {wav.name}", file=sys.stderr)
                continue
            out.append({"id": Path(e["audio"]).stem[:60], "wav": wav, "split": s,
                        "spoken": e.get("spoken", ""), "reference": e["reference"],
                        "category": e.get("category", "")})
    return out


# ── Audio surgery ────────────────────────────────────────────────────────────
def room_tone(audio: np.ndarray, seconds: float, seed: int) -> np.ndarray:
    """`seconds` of the recording's own quietest 250 ms, tiled with crossfades."""
    win = SR // 4
    if len(audio) < 2 * win:
        return np.zeros(int(seconds * SR), np.float32)
    hop = win // 2
    starts = range(0, len(audio) - win, hop)
    quiet = min(starts, key=lambda s: float(np.mean(np.square(audio[s:s + win]))))
    tile = audio[quiet:quiet + win].astype(np.float32)
    fade = SR // 100
    ramp = np.linspace(0, 1, fade, dtype=np.float32)
    rng = np.random.default_rng(seed)
    need, parts, total = int(seconds * SR), [], 0
    while total < need + fade:
        t = (tile if rng.random() < 0.5 else tile[::-1]).copy()
        t[:fade] *= ramp
        t[-fade:] *= ramp[::-1]
        parts.append(t)
        total += len(t)
    return np.concatenate(parts)[:need]


def splice(audio: np.ndarray, cuts, seconds: float, seed: int = 0) -> np.ndarray:
    """Insert `seconds` of room tone at each sample index in `cuts` (10 ms fades at the joins)."""
    fade = SR // 100
    ramp = np.linspace(0, 1, fade, dtype=np.float32)
    parts, pos = [], 0
    for k, c in enumerate(sorted(cuts)):
        head = audio[pos:c].copy()
        if len(head) > fade:
            head[-fade:] *= ramp[::-1]
        parts += [head, room_tone(audio, seconds, seed + k)]
        pos = c
    tail = audio[pos:].copy()
    if parts and len(tail) > fade:
        tail[:fade] *= ramp
    return np.concatenate(parts + [tail]).astype(np.float32)


def word_times(engine, audio: np.ndarray):
    """[(word, start_s, end_s)] from one plain pass (no prompt, no VAD)."""
    segments, _ = engine.model.transcribe(audio, language="en", beam_size=5, vad_filter=False,
                                          word_timestamps=True, condition_on_previous_text=False)
    return [(w.word.strip(), float(w.start), float(w.end)) for s in segments for w in (s.words or [])]


def _bare(word: str) -> str:
    return re.sub(r"[^a-z0-9]", "", word.lower())


def pause_sites(words, every_s: float = 7.0):
    """
    Mid-clause word gaps, about one per `every_s`: no punctuation before the gap,
    lower-case word after it, and no spoken-command word within two words.
    Returns sample indices (the midpoint of each chosen gap).
    """
    sites, last = [], 0.0
    for i in range(1, len(words) - 2):
        (w0, _s0, e0), (w1, s1, _e1) = words[i], words[i + 1]
        near = {_bare(w[0]) for w in words[max(0, i - 2):i + 4]}
        if (w0 and w0[-1].isalnum() and w1[:1].islower() and not near & _COMMAND_WORDS
                and e0 - last >= every_s):
            sites.append(int((e0 + s1) / 2 * SR))
            last = e0
    return sites


def command_sites(words):
    """Sample indices just before and just after every spoken command phrase."""
    sites = []
    bare = [_bare(w[0]) for w in words]
    for i in range(len(words) - 1):
        pair = (bare[i], bare[i + 1])
        if pair in (("new", "line"), ("next", "line"), ("new", "paragraph"), ("open", "quote"),
                    ("open", "quotes"), ("close", "quote"), ("close", "quotes"), ("end", "quote")):
            if i > 0:
                sites.append(int((words[i - 1][2] + words[i][1]) / 2 * SR))
            if i + 2 < len(words):
                sites.append(int((words[i + 1][2] + words[i + 2][1]) / 2 * SR))
    return sorted(set(sites))


def build_condition(name: str, audio: np.ndarray, words):
    """(audio, stop_at_sample or None, number of pause sites) for a condition; None if not applicable."""
    if name == "orig":
        return audio, None, 0
    if name in ("pause1.5", "pause4"):
        sites = pause_sites(words)
        return (splice(audio, sites, float(name[5:])), None, len(sites)) if sites else None
    if name == "cmdpause":
        sites = command_sites(words)
        return (splice(audio, sites, 2.0), None, len(sites)) if sites else None
    if name == "tailpause":
        if len(words) < 6:
            return None
        cut = int((words[-3][2] + words[-2][1]) / 2 * SR)
        end = min(len(audio), int(words[-1][2] * SR) + SR // 2)
        return splice(audio[:end], [cut], 3.0), None, 1
    if name == "earlystop":
        if len(words) < 3:
            return None
        return audio, max(0, int((words[-1][2] - 0.15) * SR)), 0
    raise SystemExit(f"unknown condition {name}")


# ── Running the app pipeline ─────────────────────────────────────────────────
class FileMic:
    """
    A whole recording served as fast as it is read. With stop_at, the read that
    crosses that sample asks for Stop (on another thread, as the GUI would) and
    later reads are paced in real time, like a microphone that is still open.
    """

    def __init__(self, pcm16: np.ndarray, stop_at=None):
        self.data, self.pos = pcm16.tobytes(), 0
        self.stop_at = None if stop_at is None else stop_at * 2
        self.on_stop = None
        self._asked = False

    def read(self, n, exception_on_overflow=False):
        if self._asked:
            time.sleep(n / SR)
        chunk = self.data[self.pos:self.pos + 2 * n]
        self.pos += len(chunk)
        if self.stop_at is not None and not self._asked and self.pos >= self.stop_at:
            self._asked = True
            threading.Thread(target=self.on_stop, daemon=True).start()
        return chunk

    def stop_stream(self):
        pass

    def close(self):
        pass


def run_pipeline(engine, audio, stop_at, style, builder, post, profile, with_spoken=False):
    """
    Final text (as the GUI would copy it) and the raw per-chunk pieces. With
    with_spoken, the text before spoken commands are converted is appended.
    """
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    mic = FileMic(pcm, stop_at)
    if getattr(post, "corrector", None) is not None:
        post.corrector.same_sound = bool(profile.get("extra_fixes"))
    t = ChunkedTranscriber(engine, style, stream_factory=lambda: (mic, None),
                           prompt_builder=builder, postprocess=post, **profile.get("transcriber", {}))
    mic.on_stop = t.stop_recording
    t0 = time.perf_counter()
    t.start_recording()
    if stop_at is None:
        t._capture_thread.join()
        t.stop_recording()
    else:
        t._stopped.wait(30)
    t.wait_until_idle()
    text = t.text
    final = text_fixes.format_readings(text) if profile.get("extra_fixes") else text
    final = voice_commands.apply(final, **profile.get("commands", {}))
    out = (final, list(t.transcriptions), time.perf_counter() - t0, t.rescued_commands)
    return out + (text,) if with_spoken else out


# ── Scoring ──────────────────────────────────────────────────────────────────
def structure(text: str):
    """The formatting skeleton: paragraph/line breaks, quote marks and list numbers, in order."""
    return re.findall(r"\n\n+|\n|\"|(?:(?<=\n)|^)\d{1,2}\. ", re.sub(r"[ \t]+\n", "\n", text.strip()))


def format_ok(reference: str, hyp: str) -> bool:
    return structure(reference) == structure(hyp) and not _COMMAND_RE.search(hyp)


def _tokens(text: str):
    """[(normalised word, ends a sentence?)] in order."""
    out = []
    for raw in text.split():
        norm = normalize_words(raw)
        if norm:
            out.append((" ".join(norm), raw.rstrip('"\')')[-1:] in _TERMINAL))
    return out


def added_breaks(orig_text: str, text: str) -> int:
    """Sentence ends present after a word in `text` but not after the same word in `orig_text`."""
    a, b = _tokens(orig_text), _tokens(text)
    n = 0
    for op, i, j in align([w for w, _ in a], [w for w, _ in b]):
        if op == "ok" and b[j][1] and not a[i][1] and j < len(b) - 1:
            n += 1
    return n


def sentence_end_errors(reference: str, text: str):
    """(missing, extra) sentence ends against the reference, on the words both have."""
    a, b = _tokens(reference), _tokens(text)
    missing = extra = 0
    for op, i, j in align([w for w, _ in a], [w for w, _ in b]):
        if op == "ok" and i < len(a) - 1 and j < len(b) - 1:
            missing += a[i][1] and not b[j][1]
            extra += b[j][1] and not a[i][1]
    return missing, extra


def command_hits(reference: str, text: str):
    """(expected, found, extra) formatting marks: in-order matches of the two skeletons."""
    import difflib
    kind = lambda x: "P" if x.startswith("\n\n") else "L" if x == "\n" else "Q" if x == '"' else "N"
    a, b = [kind(x) for x in structure(reference)], [kind(x) for x in structure(text)]
    hit = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return len(a), hit, len(b) - hit


def word_edits(a: str, b: str) -> int:
    return sum(op != "ok" for op, _i, _j in align(normalize_words(a), normalize_words(b)))


def tail_ok(reference: str, hyp: str) -> bool:
    ref, h = normalize_words(reference), normalize_words(hyp)
    return bool(ref) and all(w in h[-8:] for w in ref[-3:])


def score_row(e, cond, text, base_text, audio_s, sites=0, rescued=0, elapsed_s=0.0, pieces=()):
    """One result row: `text` for recording `e` under `cond`; base_text is the same system's `orig` text."""
    paused = base_text is not None and cond != "orig"
    missing, extra = sentence_end_errors(e["reference"], text)
    return {
        "id": e["id"], "split": e["split"], "category": e["category"], "condition": cond,
        "audio_s": round(audio_s, 2), "sites": sites, "ref_words": len(normalize_words(e["reference"])),
        "errors": word_edits(e["reference"], text),
        "drift": word_edits(base_text, text) if paused else 0,
        "breaks": added_breaks(base_text, text) if paused else 0,
        "sent_missing": missing, "sent_extra": extra, "rescued": rescued,
        "commands": command_hits(e["reference"], text),
        "uses_format": bool(structure(e["reference"])),
        "format_ok": format_ok(e["reference"], text),
        "tail_ok": tail_ok(e["reference"], text),
        "elapsed_s": round(elapsed_s, 2), "text": text, "pieces": list(pieces),
    }


def summarise(rows, conditions):
    summary = {}
    for cond in conditions:
        r = [x for x in rows if x["condition"] == cond]
        if not r:
            continue
        fmt = [x for x in r if x["uses_format"]]
        summary[cond] = {
            "recordings": len(r), "sites": sum(x["sites"] for x in r),
            "wer": round(100 * sum(x["errors"] for x in r) / max(1, sum(x["ref_words"] for x in r)), 2),
            "breaks": sum(x["breaks"] for x in r), "drift": sum(x["drift"] for x in r),
            "sent_missing": sum(x["sent_missing"] for x in r), "sent_extra": sum(x["sent_extra"] for x in r),
            "rescued": sum(x["rescued"] for x in r), "elapsed_s": round(sum(x["elapsed_s"] for x in r), 1),
            "format": f"{sum(x['format_ok'] for x in fmt)}/{len(fmt)}",
            "commands": f"{sum(x['commands'][1] for x in r)}/{sum(x['commands'][0] for x in r)}"
                        f"+{sum(x['commands'][2] for x in r)}",
            "tail": f"{sum(x['tail_ok'] for x in r)}/{len(r)}",
        }
    return summary


def print_summary(summary):
    print(f"{'condition':10s} {'n':>3s} {'sites':>5s} {'WER %':>6s} {'breaks':>6s} {'drift':>5s} {'format':>7s} "
          f"{'tail':>6s} {'s-miss':>6s} {'s-extra':>7s} {'commands':>9s} {'rescued':>7s} {'secs':>6s}")
    for cond, s in summary.items():
        print(f"{cond:10s} {s['recordings']:3d} {s['sites']:5d} {s['wer']:6.2f} {s['breaks']:6d} "
              f"{s['drift']:5d} {s['format']:>7s} {s['tail']:>6s} {s['sent_missing']:6d} {s['sent_extra']:7d} "
              f"{s['commands']:>9s} {s['rescued']:7d} {s['elapsed_s']:6.1f}")


def cached_word_times(cache_dir: Path, audio: np.ndarray, engine=None):
    """Word timings for a recording from the cache; computed with `engine` when missing."""
    cache = cache_dir / f"{hashlib.sha256(audio.tobytes()).hexdigest()[:16]}.json"
    if cache.is_file():
        return [tuple(w) for w in json.loads(cache.read_text(encoding="utf-8"))]
    if engine is None:
        raise SystemExit(f"no cached word timings ({cache.name}); run dictation_reliability.py on this split first")
    words = word_times(engine, audio)
    cache.write_text(json.dumps(words), encoding="utf-8")
    return words


ENGINES = ("whisper", "parakeet", "parakeet-v3", "canary", "medasr")


def style_for(profile: dict) -> str:
    """The style prompt the app would use for these options (a dictated example with Spoken punctuation)."""
    style = load_prompt()
    if profile.get("commands", {}).get("punctuation"):
        style = (style + " " + voice_commands.DICTATION_EXAMPLE).strip()
    return style


def make_engine(name: str = "whisper", model=None, profile=None):
    """
    The recogniser for a run. "whisper" is the app's engine (large-v3, as the
    hardware profile picks it); the others are trial engines that need their
    own environment (see src/onnx_engine.py, src/medasr_engine.py).
    """
    if name == "whisper":
        register_cuda_dll_dirs()
        cfg = choose_config(detect_hardware(), accurate=True)
        if model:
            cfg.model = model
        engine = FasterWhisperEngine(cfg)
        engine.warmup()
        for key, value in (profile or {}).get("engine", {}).items():
            setattr(engine, key, value)
        return engine
    if name == "medasr":
        from medasr_engine import MedASREngine
        if not model:
            raise SystemExit("--model <verified MedASR snapshot folder> is required for medasr")
        return MedASREngine(Path(model))
    from onnx_engine import OnnxAsrEngine
    engine = OnnxAsrEngine(name)
    engine.warmup()
    return engine


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--split", default="dev", choices=["dev", "held", "all"])
    ap.add_argument("--profile", default="baseline", choices=sorted(PROFILES))
    ap.add_argument("--conditions", default=",".join(CONDITIONS))
    ap.add_argument("--model")
    ap.add_argument("--only", help="substring of recording ids to keep")
    ap.add_argument("--engine", default="whisper", choices=ENGINES)
    args = ap.parse_args(argv)

    profile = PROFILES[args.profile]
    entries = load_corpus(args.corpus_root, args.split)
    if args.only:
        entries = [e for e in entries if args.only in e["id"]]
    if not entries:
        raise SystemExit("no recordings found")
    args.out.mkdir(parents=True, exist_ok=True)
    cache_dir = args.out.parent / "word_times"
    cache_dir.mkdir(exist_ok=True)

    engine = make_engine(args.engine, args.model, profile)
    cfg = engine.config
    style = style_for(profile)
    builder, post = build_text_pipeline(style, count=getattr(engine, "count_tokens", None), env={})
    tag = args.profile if args.engine == "whisper" else f"{args.engine}_{args.profile}"

    rows, t_start = [], time.perf_counter()
    for e in entries:
        audio = load_wav(e["wav"])
        words = cached_word_times(cache_dir, audio, engine if args.engine == "whisper" else None)
        base_text = None
        for cond in args.conditions.split(","):
            built = build_condition(cond, audio, words)
            if built is None:
                continue
            cond_audio, stop_at, sites = built
            text, pieces, elapsed, rescued = run_pipeline(engine, cond_audio, stop_at, style, builder, post, profile)
            if cond == "orig":
                base_text = text
            rows.append(score_row(e, cond, text, base_text, audio_s=len(cond_audio) / SR, sites=sites,
                                  rescued=rescued, elapsed_s=elapsed, pieces=pieces))
        print(f"{e['id'][:40]:40s} done ({time.perf_counter() - t_start:.0f}s)", flush=True)

    summary = summarise(rows, args.conditions.split(","))
    result = {"profile": args.profile, "settings": profile, "split": args.split,
              "model": cfg.model, "compute_type": engine.config.compute_type, "device": engine.config.device,
              "summary": summary, "rows": rows}
    (args.out / f"{tag}__{args.split}.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

    print(f"\nprofile={tag} split={args.split} model={Path(str(cfg.model)).name} "
          f"{engine.config.device}/{engine.config.compute_type}")
    print_summary(summary)


if __name__ == "__main__":
    main()
