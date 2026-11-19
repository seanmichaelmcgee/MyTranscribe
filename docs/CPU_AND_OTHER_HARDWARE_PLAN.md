# Running without an NVIDIA card: test and distribution plan

Status: phase 1 built 2026-11-19 (small.en on the processor, and a Windows installer); not yet
tried on a real laptop. Other graphics cards (Vulkan) next; Apple (Metal) later.

The goal stays the same: high-quality English medical dictation with an ordinary microphone.
A setup is only offered to testers once it has been measured on the same fictional reading
set as the NVIDIA build, for both accuracy and the wait after Stop.

## Where things stand

- The app runs Whisper through faster-whisper (CTranslate2), which uses an NVIDIA card (CUDA)
  or the processor. There is no Vulkan, AMD, Intel-graphics or Apple-GPU path in it.
- With no NVIDIA card, `src/hw_profile.py` already falls back to the processor: model
  `small.en`, int8, all cores but one. That fallback has never been tested as a setup someone
  would dictate with, and `small.en` has not been measured on medical dictation.
- On an NVIDIA card (RTX 4070 Ti SUPER, and a 6 GB GTX 1660 Ti) large-v3 gives the figures in
  the README; text is ready about 1 to 3 seconds after Stop.

### First measurement: large-v3 on the processor alone

Intel Core i9-14900KF (24 cores, a fast desktop processor), int8, the app's own engine and
settings, a 60-second fictional consult letter in 30-second pieces and a 7-second message.
Only large-v3 was on the PC; no other model was tried yet.

| Threads | Beam | Letter: compute for 60 s of speech | Speed (compute ÷ audio) | 7 s message: wait after Stop |
|---|---|---|---|---|
| 24 | 5 | 30 s | 0.50 | 6.3 s |
| 8 | 5 | 28 s | 0.47 | 6.3 s |
| 4 | 5 | 30 s | 0.50 | 7.1 s |
| 4 | 1 | 19 s | 0.32 | 6.2 s |

What it says:

- On a fast desktop processor large-v3 keeps up with speech (it needs about half as long as
  the speech lasts), so long dictation works, but **a short message waits about as long as it
  took to say** (6 to 7 seconds), against about a second on a graphics card.
- More threads did not help past four: the model is limited by memory speed, not core count.
  Capping the threads on this machine therefore does **not** imitate a slower PC; an ordinary
  clinic desktop or laptop is likely to be two to four times slower, and large-v3 would then
  fall behind live dictation.
- A narrower search (beam 1) cut the letter's compute by a third but not the short message's
  wait: for short pieces the fixed cost of reading the audio (the encoder) dominates, and only
  a smaller model reduces that.
- So the processor-only build needs a smaller model, chosen by measurement, not by guess.

### Phase 1 result (2026-11-19): small.en, 3 beams, and an installer

- **The four candidates were measured** (`large-v3-turbo`, `distil-large-v3.5`, `medium.en`,
  `small.en`):
  - speed on four laptop-class cores (this PC's efficiency cores, pinned);
  - accuracy on the owner's 47 real recordings.

  Only small.en keeps up on a laptop: about 3 s after a 7.5 s message and 6 s for 30 s of
  speech on those cores. The larger models need 10 to 12 s for the same message. Full table:
  [installer/README.md](../installer/README.md).
- **The real app in real time on those cores** (23 held-out recordings): median wait after Stop
  3.6 s (3.0 to 9.3 s), and 5.88% word errors. With the two changes below (installed build
  plus update 2026.11.19.3): median 1.9 s (1.3 to 7.5 s; short messages 1.3 to 2.1 s), 5.95%.
- **Cost:** small.en makes 9.98% word errors and gets 36 of 314 medical words wrong, against
  7.47% and 12 for large-v3 on a graphics card.
- **App changes:**
  - on the processor, 3 beams with patience 1: same accuracy as 5 beams and patience 2, about
    30% faster;
  - one thread per physical core;
  - no second listen for a dropped "new paragraph" on the processor (each is a whole model
    pass, 2 to 2.5 s on those cores; on the 47 recordings they ran 8 times and changed nothing);
  - a short piece (up to 16 s of speech) is encoded in a window of its speech plus 2 s (at least
    10 s) instead of Whisper's full 30 s. The encoder costs the same for 3 s of speech as for 30,
    so this is most of the wait after a short message: on the 47 recordings the last piece's
    decode fell from 3.7 to 1.3 s (median), with 33 medical words wrong instead of 38 and 9.83%
    word errors instead of 10.05%. Long pieces keep 30 s: shortening them saved little and once
    made the model skip a sentence;
  - an NVIDIA card without its libraries uses the processor;
  - the wizard states the expected wait and the extra errors.
- **Distribution:** `installer/` builds a per-user Windows installer, with Python, the packages
  and small.en inside, and no NVIDIA libraries. Code signing and the licences of the bundled
  parts are still to decide before testers get it.
- **Not yet measured:** a real 5-year-old laptop. The decision rule below (under 3 s after a
  short message) is probably missed by a few seconds on one.

## Phase 1: processor-only Windows (now)

1. **Candidate models**, all MIT-licensed faster-whisper conversions on Hugging Face (each needs
   a one-time download, about 0.5 to 1.6 GB, with the owner's go-ahead):
   `large-v3-turbo`, `distil-large-v3.5`, `medium.en`, `small.en`, and large-v3 for reference.
2. **Accuracy** on the fictional reading sets already recorded (v1, 26 items; v2, 5 items),
   scored exactly as for the graphics-card build: word errors, drug names, doses, commands,
   last words. Beam 5 and beam 1 for each.
3. **Speed**: compute ÷ audio and the wait after Stop for a short message and a letter, at the
   app's settings. Measured on this PC and, before release, on at least one ordinary laptop or
   clinic desktop (4 to 8 cores, no graphics card): that is the machine testers will have.
4. **Decision rule**: the most accurate model that, on the ordinary machine, keeps the
   compute under about 0.5 × the speech (so it keeps up with margin) and the wait after a short
   message under about 3 seconds. If nothing meets it, shorter pieces for short messages, or
   telling CPU users which kind of dictation it suits, are the fall-backs to try.
5. **Then change the app**: the CPU default model in `hw_profile.py`; Options → Accuracy on a
   processor-only PC chooses between the two best models found; the status line says
   "processor only" so nobody mistakes slow for broken.
6. **Distribution**: a processor-only install does not need the NVIDIA libraries (about 1 GB):
   a `requirements-cpu.txt` and a setup choice. For testers who should not have to install
   Python, a packaged installer (bundled Python, model downloaded on first start after asking)
   is the next step; an unsigned installer triggers Windows SmartScreen warnings, so code
   signing needs a decision before wide distribution.

## Phase 2: other graphics cards through Vulkan (AMD, Intel, integrated graphics)

- **Route:** add a [whisper.cpp](https://github.com/ggml-org/whisper.cpp) engine behind the
  existing engine contract (`src/engines.py`), so chunking, prompts, the medical clean-up and
  every option apply unchanged. whisper.cpp has a Vulkan back end that runs on AMD, Intel and
  NVIDIA cards; one published comparison put large-v3 at about five times faster than an
  8-core processor on an AMD RX 6800 (Linux).
- **To check before building on it:**
  - the official Windows releases do not include a Vulkan build, so it must be built from
    source or taken from a community build; the Python bindings
    ([pywhispercpp](https://github.com/abdeladim-s/pywhispercpp)) document a Vulkan build flag;
  - the vocabulary prompt (the app's main accuracy lever), word timings (needed for
    pause-aware dictation) and voice-activity filtering all have to work through the bindings;
  - whisper.cpp falls back to the processor silently if the graphics back end fails, so the
    app must detect and say which one it is using;
  - its model files are converted and may be quantised differently (q5/q8), so accuracy must be
    re-measured, not assumed; some drivers have had Vulkan shader problems with quantised models.
- **Alternative considered:** CTranslate2 (what the app uses now) gained AMD ROCm support in
  version 4.7.0 (2026), but on Windows it means building from source and covers only recent AMD
  cards (RX 6000 and 7000). One engine that covers AMD, Intel and later Apple is the better
  investment.
- **Validation gate:** same reading sets; within about half a point of the NVIDIA build's word
  errors with every drug name right, and a comparable wait after Stop, on at least one AMD and
  one Intel machine.

## Phase 3: Apple computers (Metal), later

whisper.cpp also runs on Apple silicon (Metal, Core ML), so the Phase 2 engine carries over.
The rest of the app is Windows-specific today and needs porting: the global keys and mouse
button (macOS accessibility permission), the clipboard privacy marking and paste
(`phi_clipboard.py`), and packaging and signing for macOS. Same validation gate.

## Not in this plan

Validation on many clinicians' voices is a separate piece of work (see `docs/VALIDATION.md`).
