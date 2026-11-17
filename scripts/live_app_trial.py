"""
Live trial of the real app window: recordings are played in real time through
the virtual audio cable (VB-CABLE) and captured by the app's own microphone
path, started and stopped the way the hotkey does it.

Unlike dictation_reliability.py (files pushed through the pipeline as fast as
it will take them), this exercises the always-open microphone and its
pre-roll, real-time chunking while audio is still arriving, the post-roll after
Stop, the window's polling and the final copy. It measures what a person
waits for: seconds from Stop to the finished text.

    live_app_trial.py --corpus-root results_1060 --out results_1060/reliability/live --split held \
        --options pause_aware,spoken_punctuation,extra_fixes [--engine whisper] [--limit 5]

The window appears on screen while it runs. Your own settings file, clipboard
and hotkeys are not touched: settings live in the output folder, the copy goes
to an in-memory clipboard, and no global key or mouse hook is installed.
Chimes are muted. Audio leaves through "CABLE Input" only.
"""

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE.parent / "tests"))

import dictation_reliability as dr  # noqa: E402
import dragon_replay  # noqa: E402

CABLE_CAPTURE_PREFIX = "CABLE Output"
OPTIONS = ("pause_aware", "spoken_punctuation", "extra_fixes", "only_dictated_commas")


def cable_stream_factory():
    """Open the cable's recording end as the app's microphone: (stream, pyaudio)."""
    import pyaudio
    from chunked_transcriber import FRAMES_PER_BUFFER, SAMPLE_RATE
    pa = pyaudio.PyAudio()
    found = [d for d in (pa.get_device_info_by_index(i) for i in range(pa.get_device_count()))
             if d["maxInputChannels"] > 0 and d["name"].startswith(CABLE_CAPTURE_PREFIX)
             and pa.get_host_api_info_by_index(d["hostApi"])["name"] == "MME"]
    if len(found) != 1:
        pa.terminate()
        raise RuntimeError(f"expected one '{CABLE_CAPTURE_PREFIX}' recording device, found {len(found)}")
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE, input=True,
                     input_device_index=int(found[0]["index"]), frames_per_buffer=FRAMES_PER_BUFFER)
    return stream, pa


def pump(app, until, timeout_s):
    """Run the Qt event loop until until() is true; False on timeout."""
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        app.processEvents()
        if until():
            return True
        time.sleep(0.01)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--corpus-root", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--split", default="held", choices=["dev", "held"])
    ap.add_argument("--options", default=",".join(OPTIONS), help="comma list of " + ", ".join(OPTIONS) + " (or none)")
    ap.add_argument("--engine", default="whisper",
                    help="recogniser, or a comma list to switch between in the same running window "
                         "(as Options -> Recogniser does): whisper,medasr,parakeet,canary")
    ap.add_argument("--model", help="local Whisper model folder (sets MYTRANSCRIBE_MODEL)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    ap.add_argument("--tail-s", type=float, default=0.4, help="silence between the last sample and Stop")
    args = ap.parse_args(argv)
    on = {o for o in args.options.split(",") if o and o != "none"}
    if on - set(OPTIONS):
        raise SystemExit(f"unknown option(s): {sorted(on - set(OPTIONS))}")

    entries = dr.load_corpus(args.corpus_root, args.split)
    if args.only:
        entries = [e for e in entries if args.only in e["id"]]
    entries = entries[:args.limit] if args.limit else entries
    if not entries:
        raise SystemExit("no recordings found")
    args.out.mkdir(parents=True, exist_ok=True)

    import chunked_transcriber
    chunked_transcriber._default_stream_factory = cable_stream_factory   # the app's microphone is the cable
    from PyQt6.QtWidgets import QApplication
    import gui_med
    from fakes import FakeClipboard
    from settings import Settings

    app = QApplication.instance() or QApplication([])
    import os
    from dataclasses import replace
    engine_names = args.engine.split(",")
    if args.model:
        os.environ["MYTRANSCRIBE_MODEL"] = args.model
    settings = Settings(start_compact=True, chime_volume=0, autopaste=False, live_insert=False,
                        keep_mic_ready=True, voice_commands=True, engine=engine_names[0],
                        **{o: o in on for o in OPTIONS})
    window = gui_med.MedTranscriptionWindow(autopaste=False, settings=settings,
                                            settings_path=args.out / "trial_settings.json", install_hooks=False)
    window._confirm_download = lambda engine: False      # a trial never downloads: fail instead
    clip = FakeClipboard()
    window._clipboard = lambda: clip
    window._clipboard_seq = clip.sequence
    window.show()
    if not pump(app, lambda: window.ready or window._load_error, 300) or window._load_error:
        raise SystemExit(f"app did not become ready: {window._load_error}")
    pump(app, lambda: False, 1.5)                      # let the always-open microphone fill its pre-roll

    for position, engine_name in enumerate(engine_names):
        if position:
            switched = time.monotonic()
            window.apply_settings(replace(window._settings, engine=engine_name))   # what Save in Options does
            if not pump(app, lambda: window.ready or window._load_error, 300) or window._load_error:
                raise SystemExit(f"switch to {engine_name} failed: {window._load_error}")
            print(f"switched to {engine_name} in {time.monotonic() - switched:.1f} s", flush=True)
            pump(app, lambda: False, 1.5)
        run_engine(args, app, window, entries, engine_name, on)
    window.close()


def run_engine(args, app, window, entries, engine_name, on):
    tag = f"{engine_name}__{'+'.join(sorted(on)) or 'none'}__{args.split}"
    rows, waits = [], []
    for n, e in enumerate(entries, 1):
        audio = dr.load_wav(e["wav"])
        pcm = dragon_replay.pcm16(audio)
        window._copied_text = None
        window.on_hotkey()                             # Start, as the hotkey does it
        pump(app, lambda: False, 0.3)
        player = threading.Thread(target=dragon_replay.play, args=(pcm,), daemon=True)
        player.start()
        pump(app, lambda: not player.is_alive(), len(audio) / dr.SR + 30)
        pump(app, lambda: False, args.tail_s)
        stopped = time.monotonic()
        window.on_hotkey()                             # Stop
        if not pump(app, lambda: not window._finishing, 180):
            raise SystemExit(f"{e['id']}: the app was still transcribing after 180 s")
        wait = time.monotonic() - stopped
        text = window._copied_text or ""
        waits.append(wait)
        row = dr.score_row(e, "orig", text, text, audio_s=len(audio) / dr.SR, elapsed_s=wait)
        rows.append(row)
        print(f"{n}/{len(entries)} {len(audio) / dr.SR:5.1f} s audio, text {wait:4.1f} s after Stop", flush=True)
        pump(app, lambda: False, 1.0)

    summary = dr.summarise(rows, ["orig"])
    result = {"tag": tag, "options": sorted(on), "engine": engine_name, "summary": summary,
              "stop_to_text_s": {"median": round(statistics.median(waits), 2), "max": round(max(waits), 2)},
              "rows": rows}
    (args.out / f"{tag}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nlive {tag}: Stop-to-text median {result['stop_to_text_s']['median']} s, max {result['stop_to_text_s']['max']} s")
    dr.print_summary(summary)


if __name__ == "__main__":
    main()
