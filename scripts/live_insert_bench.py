"""
live_insert_bench.py: "type as you dictate" (Options -> Type into my document while I
dictate) against the normal copy-at-Stop text, at several chunk lengths.

For every recording the app pipeline runs once (faster than real time). From that run:

  * final     the text the app copies at Stop (whole transcript formatted at once)
  * inserted  what live insert types: each finished piece formatted on its own and
              joined the way gui_med joins them (a space unless the piece starts a line)

Both are scored against the script. Timing is replayed on a real-time clock from the
measured decode times: a chunk can start decoding only once its audio has been
spoken and the previous chunk is done. That gives how long after the end of a
piece's audio its text appears, how often text appears, and Stop -> last text.

    python scripts/live_insert_bench.py --corpus-root results_1060 --out results_1060/live_insert \
        --model <large-v3 folder> --chunks 30,15,10,5

Writes <out>/<tag>.json (per-recording rows, private: results_1060 is ignored by git)
and prints totals only.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import dictation_reliability as dr                                  # noqa: E402
import live_insert                                                  # noqa: E402
import validation_tool as vt                                        # noqa: E402
from chunked_transcriber import ChunkedTranscriber                  # noqa: E402
from vocab import build_text_pipeline                               # noqa: E402
import text_fixes                                                   # noqa: E402
import voice_commands                                               # noqa: E402

SR = 16000
SENTENCE_END = ('.', '?', '!', ':', '"', '\n')


class TimedTranscriber(ChunkedTranscriber):
    """Records when each chunk was queued (audio seconds) and how long each decode took."""

    def start_recording(self, mode="normal"):
        self.enqueued_at, self.decodes = [], []
        super().start_recording(mode)

    def _enqueue(self, pcm):
        if pcm:
            self.enqueued_at.append(self._captured_samples / SR)
        super()._enqueue(pcm)

    def _transcribe_pause_aware(self, chunk, final):
        t0 = time.perf_counter()
        out = super()._transcribe_pause_aware(chunk, final)
        self.decodes.append((time.perf_counter() - t0, len(self.transcriptions)))
        return out

    def _transcribe_chunk(self, chunk):
        t0 = time.perf_counter()
        super()._transcribe_chunk(chunk)
        self.decodes.append((time.perf_counter() - t0, len(self.transcriptions)))


def fmt(text, profile):
    if profile.get("extra_fixes"):
        text = text_fixes.format_readings(text)
    return voice_commands.apply(text, **profile.get("commands", {}))


def typed_text(raw_pieces, profile):
    """What live insert types now: the stable new part of the whole transcript formatted so far."""
    doc, done = "", []
    for p in raw_pieces:
        done.append(p)
        doc += live_insert.next_text(doc, fmt(" ".join(done), profile))
    return doc + live_insert.next_text(doc, fmt(" ".join(done), profile), final=True)


def join_inserted(pieces):
    """The first version of live insert: each piece formatted alone, a space between pieces unless one starts a line."""
    out, any_yet = "", False
    for p in pieces:
        if any_yet and not p.startswith("\n"):
            p = " " + p
        out += p
        any_yet = True
    return out


def replay_clock(enqueued_at, decodes, audio_s):
    """Real-time schedule from measured decode times -> (piece delays, gaps between pieces, stop->last text)."""
    finish, prev, appear = 0.0, 0.0, []
    stop = audio_s
    for k, (dur, n_after) in enumerate(decodes):
        ready = enqueued_at[k] if k < len(enqueued_at) else stop
        start = max(ready, prev)
        prev = start + dur
        appear.append((ready, prev, n_after))
    delays, times, last_n = [], [], 0
    for ready, done, n_after in appear:
        if n_after > last_n:                      # this decode committed new text
            delays.append(done - ready)
            times.append(done)
            last_n = n_after
    gaps = [b - a for a, b in zip(times, times[1:])]
    return delays, gaps, (prev - stop) if appear else 0.0


def corpus(root: Path, heldout_root: Path):
    items = []
    for e in dr.load_corpus(heldout_root, "held"):
        items.append(dict(e, set="held-out"))
    for session, set_file in (("owner1", "validation_set_v1.txt"), ("owner2", "validation_set_v2.txt")):
        folder = root / "validation" / session / "session" / "items"
        for it in vt.load_set(ROOT / "validation" / set_file):
            wav = folder / f"{it['id']}.wav"
            if wav.is_file():
                items.append({"id": f"{session}-{it['id']}", "wav": wav, "split": "validation", "set": session,
                              "spoken": it["spoken"], "reference": it["reference"], "category": it["category"]})
    return items


def load_wav(path):
    import wave
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


def run(engine, items, chunk_s, profile, style, builder, post, carry_s=None):
    """carry_s: longest unfinished sentence carried into the next window (default: the app's rule)."""
    rows = []
    for e in items:
        audio = load_wav(e["wav"])
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        mic = dr.FileMic(pcm)
        if getattr(post, "corrector", None) is not None:
            post.corrector.same_sound = bool(profile.get("extra_fixes"))
        t = TimedTranscriber(engine, style, stream_factory=lambda: (mic, None), prompt_builder=builder,
                             postprocess=post, chunk_target_s=chunk_s, **profile.get("transcriber", {}))
        if carry_s is not None:
            t._carry_limit_s = carry_s
            t.set_pause_aware(t.pause_aware, t.post_roll_s)
        t.start_recording()
        t._capture_thread.join()
        t.stop_recording()
        t.wait_until_idle()
        final = fmt(t.text, profile)
        raw = [p for p in t.transcriptions if p]
        pieces = [fmt(p, profile) for p in raw]
        old = join_inserted(pieces)
        inserted = typed_text(raw, profile)
        audio_s = len(audio) / SR
        delays, gaps, stop_s = replay_clock(t.enqueued_at, t.decodes, audio_s)
        r_final = dr.score_row(e, "final", final, None, audio_s)
        r_ins = dr.score_row(e, "inserted", inserted, None, audio_s)
        r_old = dr.score_row(e, "old", old, None, audio_s)
        rows.append({
            "id": e["id"], "set": e["set"], "category": e["category"], "audio_s": round(audio_s, 1),
            "ref_words": r_final["ref_words"],
            "final_errors": r_final["errors"], "inserted_errors": r_ins["errors"], "old_errors": r_old["errors"],
            "final_format_ok": r_final["format_ok"], "inserted_format_ok": r_ins["format_ok"],
            "old_format_ok": r_old["format_ok"],
            "uses_format": r_final["uses_format"],
            "final_vs_inserted_words": dr.word_edits(final, inserted),
            "text_differs": final.strip() != inserted.strip(),
            "old_differs": final.strip() != old.strip(),
            "pieces": len(pieces),
            "mid_sentence_pieces": sum(1 for p in pieces[:-1] if not p.rstrip(" ").endswith(SENTENCE_END)),
            "delays": [round(d, 2) for d in delays], "gaps": [round(g, 2) for g in gaps],
            "stop_to_last_s": round(stop_s, 2),
            "decode_s": round(sum(d for d, _ in t.decodes), 2),
            "final": final, "inserted": inserted, "old": old, "raw_pieces": list(t.transcriptions),
        })
        print(f"  {chunk_s:>4}s {e['id'][:40]:40s} words {r_final['ref_words']:4d} "
              f"err final/inserted {r_final['errors']:3d}/{r_ins['errors']:3d} pieces {len(pieces):2d}", flush=True)
    return rows


def summary(rows):
    words = sum(r["ref_words"] for r in rows) or 1
    fmt_rows = [r for r in rows if r["uses_format"]]
    delays = [d for r in rows for d in r["delays"]]
    gaps = [g for r in rows for g in r["gaps"]]
    return {
        "recordings": len(rows), "words": words,
        "wer_final": round(100 * sum(r["final_errors"] for r in rows) / words, 2),
        "wer_inserted": round(100 * sum(r["inserted_errors"] for r in rows) / words, 2),
        "format_final": f"{sum(r['final_format_ok'] for r in fmt_rows)}/{len(fmt_rows)}",
        "format_inserted": f"{sum(r['inserted_format_ok'] for r in fmt_rows)}/{len(fmt_rows)}",
        "wer_old_typing": round(100 * sum(r["old_errors"] for r in rows) / words, 2),
        "format_old_typing": f"{sum(r['old_format_ok'] for r in fmt_rows)}/{len(fmt_rows)}",
        "recordings_where_old_typing_differs": sum(r["old_differs"] for r in rows),
        "recordings_where_inserted_differs": sum(r["text_differs"] for r in rows),
        "word_differences_inserted_vs_final": sum(r["final_vs_inserted_words"] for r in rows),
        "pieces": sum(r["pieces"] for r in rows),
        "mid_sentence_pieces": sum(r["mid_sentence_pieces"] for r in rows),
        "delay_after_piece_median_s": round(statistics.median(delays), 2) if delays else None,
        "delay_after_piece_p90_s": round(sorted(delays)[int(0.9 * (len(delays) - 1))], 2) if delays else None,
        "gap_between_pieces_median_s": round(statistics.median(gaps), 1) if gaps else None,
        "stop_to_last_median_s": round(statistics.median([r["stop_to_last_s"] for r in rows]), 2),
        "stop_to_last_max_s": round(max(r["stop_to_last_s"] for r in rows), 2),
        "decode_s": round(sum(r["decode_s"] for r in rows), 1),
        "audio_s": round(sum(r["audio_s"] for r in rows), 1),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus-root", required=True, type=Path, help="folder holding validation/<session>/session/items")
    ap.add_argument("--heldout-root", type=Path, help="results_1060 folder with the held-out manifests "
                                                      "(default: --corpus-root)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model")
    ap.add_argument("--profile", default="personal", choices=sorted(dr.PROFILES))
    ap.add_argument("--chunks", default="30,15,10,5")
    ap.add_argument("--only", help="substring of recording ids to keep")
    ap.add_argument("--tag", default="")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    profile = dr.PROFILES[args.profile]
    items = [e for e in corpus(args.corpus_root, args.heldout_root or args.corpus_root)
             if not args.only or args.only in e["id"]]
    print(f"{len(items)} recordings, {sum(len(load_wav(e['wav'])) for e in items) / SR / 60:.1f} min", flush=True)
    engine = dr.make_engine("whisper", args.model, profile)
    style = dr.style_for(profile)
    builder, post = build_text_pipeline(style, count=getattr(engine, "count_tokens", None), env=profile.get("env", {}))
    results = {}
    for spec in args.chunks.split(","):                   # "30" or "20:12" (window : longest carried sentence)
        window, _, carry = spec.partition(":")
        chunk_s, carry_s = float(window), (float(carry) if carry else None)
        rows = run(engine, items, chunk_s, profile, style, builder, post, carry_s)
        s = {"all": summary(rows)}
        for name in sorted({r["set"] for r in rows}):
            s[name] = summary([r for r in rows if r["set"] == name])
        results[spec] = s
        tag = f"{args.tag}chunk{int(chunk_s)}" + (f"c{int(carry_s)}" if carry_s is not None else "") + f"_{args.profile}"
        (args.out / f"{tag}.json").write_text(json.dumps({"summary": s, "rows": rows}, indent=1, ensure_ascii=False),
                                              encoding="utf-8")
        print(json.dumps({chunk_s: s["all"]}), flush=True)
    print("\nchunk | WER copied / typed / old typing | layout copied / typed / old | typed differs (new, old) | "
          "pieces mid-sentence | text after piece median/p90 | piece every | Stop->text median/max")
    for c, s in results.items():
        a = s["all"]
        print(f"{c:>6s} | {a['wer_final']:.2f} / {a['wer_inserted']:.2f} / {a['wer_old_typing']:.2f} | "
              f"{a['format_final']} / {a['format_inserted']} / {a['format_old_typing']} | "
              f"{a['recordings_where_inserted_differs']}, {a['recordings_where_old_typing_differs']} of {a['recordings']} | "
              f"{a['mid_sentence_pieces']}/{a['pieces']} | {a['delay_after_piece_median_s']}/{a['delay_after_piece_p90_s']} s | "
              f"{a['gap_between_pieces_median_s']} s | {a['stop_to_last_median_s']}/{a['stop_to_last_max_s']} s")


if __name__ == "__main__":
    main()
