# Stress test plan: Medical / GTX 1060 edition

Two parts:

- **Part A** was run in a cloud Linux VM (4 vCPU, 15 GB RAM, **no GPU, no microphone,
  no access to Hugging Face**). It proves the plumbing: threading, memory, failure
  handling, GUI responsiveness and the real faster-whisper/CTranslate2 call path. It
  cannot measure accuracy or GPU speed.
- **Part B** is the checklist for the real Windows machine with the GTX 1060. It answers
  the questions Part A can't: does CUDA work on Pascal with these wheels, how fast is it,
  how much VRAM does it use, how accurate is it on your voice, and does it behave in
  your EMR.

---

## Part A: VM results

### How the VM tests worked

| Piece | Real or simulated? |
|---|---|
| faster-whisper 1.2.1 / CTranslate2 4.8.2 / Silero VAD / tokenizer | **Real** |
| Model architecture (`large-v3-turbo`: 32-layer encoder, 4-layer decoder, 128 mel bins, int8) | **Real shape, random weights**, built by `scripts/make_random_whisper.py` (Hugging Face is blocked by the VM's network policy). Output text is gibberish |
| Dictation audio | espeak-ng reading a 64 s fictional referral letter, looped |
| Microphone | `LoopStream`, which serves audio at exactly real-time pace (or faster) |
| GUI | The real `MedTranscriptionWindow` under Xvfb, driven through `on_hotkey()` |

A random-weight decoder never emits "end of text", so it would decode the maximum 448
tokens on every 30 s window. To make timing realistic, decoding was capped at **120
tokens per window** (`--max-new-tokens 120`), about what 30 s of real dictation produces
(~75–90 words). Encoder cost, which dominates, is unaffected.

### Unit tests: `pytest tests` (78 tests at the time, ~10 s; now 128, see below)

**78 passed** (run under `xvfb-run` for the Qt tests). Covers:

- **GPU choice:** GTX 1060 → `large-v3-turbo` + `int8_float32`, detected either by
  compute capability or by card name on older drivers; RTX cards → `int8_float16`;
  < 3.5 GB VRAM → `small.en`; CPU fallback; environment overrides; `nvidia-smi`
  parsing, including old drivers and the Windows `NVSMI` folder.
- **Chunking:** cuts land inside pauses; **no audio lost or duplicated** (sample
  counts add up exactly); order preserved; previous text carried into the next
  chunk's prompt.
- **Robustness:** silent chunks are never sent to the model; engine errors are
  reported and later chunks continue; the 1-hour cap; microphone failure; Stop
  returns in < 0.5 s even when the model is slow; 100 sessions with no thread or
  PortAudio leaks.
- **PHI:** no temp files (`tempfile` is patched to raise) and transcript text never
  appears in logs.
- **Engine and clipboard:** faster-whisper call parameters, CUDA→CPU fallback,
  Windows DLL-folder registration, clipboard privacy formats, paste key sequence.
- **GUI:** buttons locked while loading, load-error message, live text, non-blocking
  Stop, auto-paste only after a hotkey stop and only once Ctrl/Alt are released, an
  empty result leaves the clipboard alone, auto-stop at end of capture, Long mode,
  microphone-open failure.

### Engine benchmark: `scripts/bench_engine.py` (turbo shape, CPU int8, 3 threads)

64 s espeak letter split into 30 s windows, beam 5, medical prompt on.

| Mode | Load | Warm-up | RTF mean | 30 s window takes | Peak RAM |
|---|---|---|---|---|---|
| Encoder only (`--encoder-only`) | 6.1 s | 7.7 s | 0.27 | ~8.1 s | 1.46 GB |
| Encoder + 120-token decode (`--max-new-tokens 120`) | 2.5 s | 6.9 s | 0.39 | ~11.7 s | 1.47 GB |

Takeaways:
- **Even on CPU, turbo-sized int8 keeps up with live speech** (RTF < 1), so the
  background design works there too. The automatic CPU fallback, if CUDA ever fails
  on the 1060, is slow but usable.
- **Every chunk pays for a full 30 s encoder pass, however short it is.** The
  final 4 s chunk had RTF 2.1, so the wait after Stop is roughly one chunk's compute
  time, whatever the letter's length. That's the number to minimise on the GPU.
- Load and warm-up happen in the background at startup, so they never block the window.

### Pipeline stress: `scripts/stress_pipeline.py`

All checks passed in every run.

| Scenario | Model | Result |
|---|---|---|
| **long**: 10 min dictation at **real-time pace** | turbo shape, CPU, 3 threads, 120-token cap | RTF mean **0.30** (max 0.51); queue never above **0** (keeps up live); 600.0/600.0 s reached the engine; `stop_recording()` 0.000 s; final text **12.8 s** after Stop; RSS flat at ~1.27 GB after warm-up (1130 → 1272 MB, 61 samples) |
| **long**: 60 min **flat out** (whole hour delivered instantly, worst-case backlog) | tiny shape, CPU | 3600.0/3600.0 s transcribed in 121 chunks; backlog peaked at 117 chunks and drained cleanly; RSS +253 MB at peak (= the queued audio, as designed); 1-hour cap honoured |
| **cycles**: 300 sessions of 0.2–3 s | tiny | 0 exceptions, 0 leaked threads, RSS 526 → 530 → 532 MB |
| **cycles**: 60 sessions | tiny | latency p50 1.5 s, max 1.8 s; RSS flat at 338 MB |
| **silence**: 5 min digital silence; 5 min room noise (RMS ≈ 40) | tiny | engine **never called** (0 calls), empty text |
| **silence**: clipped, 20× over-loud speech | tiny | handled, no errors |
| **faults**: USB mic "unplugged" after 75 s | tiny | session ends with a message; all 75 s before the failure transcribed |
| **faults**: engine raises "CUDA out of memory" on one chunk | tiny | one error marker, the other 4 chunks fine, marker kept out of later prompts |
| **gui**: 6 hotkey cycles, real window, live engine | turbo shape | worst UI stall **66 ms**, p99 12 ms; every cycle finished; auto-paste fired for each non-empty result |
| **gui**: 5 hotkey cycles | tiny | worst stall 226 ms (one-off, p99 13 ms) |

Possible follow-up (not needed for live use): queued chunks are held as float32, so
a worst-case backlog uses 2× the memory of keeping them as int16 until transcription.

### Bugs the tests caught (fixed before the PR)

1. **Error text fed back into Whisper.** After a failed chunk (e.g. CUDA out of memory),
   the string "[Transcription Error: …]" was included in the next chunk's context prompt,
   priming Whisper with junk. It's now excluded (`test_engine_error_is_reported_and_later_chunks_continue`).
2. **Phantom-phrase filter missed hyphenated forms** ("Bye-bye."), and the original
   `transcriber_v12` filter **deleted a real leading "Thank you"** from letters that start
   "Thank you for seeing…". The new filter only drops a chunk that is *entirely* a phantom
   phrase (`test_real_dictation_kept`).
3. **PyAudio instance leak.** Each recording opened a new PortAudio instance and never
   closed it, which would have mattered over hundreds of dictations in a day
   (`test_no_thread_or_pyaudio_leak_over_many_sessions`).
4. **Warm-up didn't warm anything.** With voice detection on, the silent warm-up clip
   never reached the GPU, so the first real dictation would have paid the CUDA start-up
   cost. Warm-up now bypasses VAD.
5. **Auto-paste focus trap.** The original hotkey brings the MyTranscribe window to the
   front, so an auto-paste would have pasted into MyTranscribe itself. In auto-paste mode
   the hotkey now leaves focus where it is, and paste waits for Ctrl/Alt to be released
   (otherwise the EMR receives Ctrl+Alt+V).

### Vocabulary and spelling correction (added later)

- **Prompt budget:** the full primary-care vocabulary is ~6,500 Whisper tokens
  (measured with the real Whisper tokenizer: ~3.0 characters per token), against a
  ~223-token prompt limit. The old static medical prompt alone used 214 tokens. The
  topic builder now keeps every prompt at ~211 tokens: style example (~60) + topic terms
  + the last ~160 characters of transcript.
- **Topic switching** (examples): "barking cough… stridor… ear painful" → `peds-acute,
  respiratory, ent-eye`; "HbA1c… metformin… semaglutide… ramipril" → `diabetes,
  hypertension`.
- **Spelling corrector vs real Whisper mistakes:** on 436 real Whisper transcriptions of
  spoken medical terms (from the Telnyx audit data), it **fixed 76, changed 0 to a wrong
  term**, and left the rest alone. The rest are mostly garbles nobody could fix safely
  ("sub jack son" for ceftriaxone). 3 more were half-fixed in the right direction. Clean
  clinical prose, including real sound-alikes (hydroxyzine/hydralazine,
  clonidine/clonazepam), is never changed. Locked in by
  `tests/data/whisper_misrecognitions.tsv`.
- **Cost:** topic prompts plus correction added ~9 % compute per chunk on the VM.
- **Unit tests:** 128 passing (adds parsing, topic scoring, budget, rotation, corrector
  regressions, template coherence and mic-simulation tests).

### What Part A cannot tell us

- Whether CTranslate2's CUDA build runs on compute capability 6.1 (Pascal).
- Real GPU speed and VRAM use.
- Accuracy (WER) on real speech, your accent, your microphone, medical vocabulary.
- Windows-only behaviour: DLL loading of cuBLAS/cuDNN, clipboard-history opt-out,
  auto-paste into your EMR (especially over Citrix/RDP), global hotkey.

---

## Part B: plan for the real machine (GTX 1060 6 GB, Windows)

**Fastest path (no microphone needed):** run `scripts\run_1060_checks.bat` (about 45–60
min unattended, or add `quick` for ~10 min). It covers B0, B1 and B2 below using
synthetic fictional dictations rendered with Windows voices through four simulated mics
(clean, headset, Tenor-style conference mic, noisy room), and writes
`results_1060\SUMMARY.txt`. Send that file back. The manual steps below remain for
digging deeper, and for B3/B4 once the Tenor mic is connected.

**Before you start:** make three test recordings with **no real patient information**
(read a made-up letter). Convert each to 16 kHz mono WAV:
`ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 out.wav`

| File | Content | Why |
|---|---|---|
| `letter2.wav` + `letter2.txt` | ~2 min, normal pace, fictional referral letter, plus the exact text you read | Accuracy (WER) |
| `letter10.wav` | ~10 min of continuous dictation (can be the 2-min letter read 5 times) | Speed / endurance |
| `quiet.wav` | ~1 min, softly spoken, with pauses and a cough | VAD / quiet speech |

Record results in the table at the bottom; paste it back to me (no transcripts needed).

### B0. GPU sanity (10 min)

```bat
nvidia-smi
venv1060\Scripts\python.exe -c "import sys; sys.path.insert(0,'src'); import fw_engine; fw_engine.register_cuda_dll_dirs(); import ctranslate2 as c; print(c.__version__, c.get_cuda_device_count(), sorted(c.get_supported_compute_types('cuda')))"
```

- [ ] `nvidia-smi` shows the GTX 1060, driver ≥ 527, "CUDA Version: 12.x".
- [ ] Python prints `4.8.2 1 [... 'int8_float32' ...]`.
- [ ] `run_1060.bat` console shows `device=cuda compute=int8_float32 model=large-v3-turbo`
      and "Warmup done".

**Most likely failure:** the CTranslate2 wheel has no kernels for Pascal ("no kernel image
is available for execution on the device"). The app falls back to CPU automatically (look
for "falling back to CPU int8"). Send me the error; the fix is pinning an older
CTranslate2 or building one with `sm_61`.

### B1. Benchmark (30 min)

```bat
set PY=venv1060\Scripts\python.exe
%PY% scripts\bench_engine.py --audio letter2.wav --reference letter2.txt --json b1_turbo.json
%PY% scripts\bench_engine.py --audio letter2.wav --reference letter2.txt --beam-size 1
%PY% scripts\bench_engine.py --audio letter2.wav --reference letter2.txt --model large-v3
%PY% scripts\bench_engine.py --audio letter2.wav --reference letter2.txt --model distil-large-v3.5
%PY% scripts\bench_engine.py --audio letter2.wav --reference letter2.txt --no-prompt
%PY% scripts\bench_engine.py --audio letter10.wav
```

Pass criteria (turbo, default settings):
- [ ] RTF mean ≤ **0.3** (a 30 s piece in ≤ 9 s; the background pipeline needs < 1.0).
- [ ] Peak GPU ≤ **4.5 GB** whole-card (leaves room for the desktop, browser and EMR).
- [ ] WER on `letter2` ≤ **8 %**. `--no-prompt` should be *worse*; if not, the prompt
      needs rewriting with your terms.
- [ ] `large-v3` fits (peak GPU < 5.5 GB). Note whether its WER is meaningfully better.

### B2. Pipeline stress with the real model (60–75 min, mostly unattended)

```bat
%PY% scripts\stress_pipeline.py --audio letter10.wav --scenario long --minutes 30 --json b2_long.json
%PY% scripts\stress_pipeline.py --audio letter2.wav --scenario cycles --cycles 200 --scenario silence --scenario faults --json b2_misc.json
%PY% scripts\stress_pipeline.py --audio letter2.wav --scenario gui --gui-cycles 20 --json b2_gui.json
```

Meanwhile run `nvidia-smi -l 10` in a second window and note the highest "MiB" used.

- [ ] Script prints **ALL CHECKS PASSED** each time.
- [ ] `long`: max queue ≤ 2, final latency ≤ 10 s, RSS flat, VRAM flat over 30 min.
- [ ] `gui`: worst UI gap < 250 ms.

### B3. Real-world use (a few days)

- [ ] **Mic:** your usual dictation mic (if it's a Nuance PowerMic, it works as a USB
      microphone; its buttons won't do anything here). Set it as the Windows default
      input device.
- [ ] **Clipboard history:** turn Win+V history on temporarily, dictate, press Win+V.
      The transcript must **not** appear. (Tests the Windows privacy formats, which can't
      be checked on Linux.) Turn history off again.
- [ ] **No files left behind:** after a day's use, `%TEMP%` contains no new `.wav`
      files from MyTranscribe, and the console shows only "Copied N chars", never text.
- [ ] **Auto-paste** (`MYTRANSCRIBE_AUTOPASTE=1`): into Word, into Outlook, into the
      EMR. If the EMR runs over Citrix/RDP, note whether the paste arrives.
- [ ] **Hotkey while the EMR has focus**, including when the EMR runs as administrator
      (Windows blocks simulated keys into elevated apps from non-elevated ones).
- [ ] **Side-by-side with Dragon:** dictate the same 10 short letters with each; count
      the corrections you had to make. This is the number that matters.
- [ ] **Length:** one real 10–15 minute letter; note the wait after Stop.

### B4. Adversarial (30 min)

- [ ] Unplug the USB mic mid-dictation: recording ends, text so far is kept, a
      "[microphone read failed…]" note appears, and the app still works after
      re-plugging and restarting.
- [ ] Teams/Zoom call open using the same mic: start dictation (shared mode should work;
      exclusive mode may fail with "Could not open the microphone").
- [ ] Play a YouTube video or game in the background (GPU busy) during a dictation:
      note the slowdown.
- [ ] Win+L lock during "[Finishing transcription…]": text is on the clipboard after
      unlocking.
- [ ] Sleep/hibernate mid-recording: app recovers or fails cleanly (note which).
- [ ] Dragon running at the same time (VRAM and mic contention).
- [ ] 16 GB RAM with many browser tabs open: no "falling behind" warnings.

### Results to send back

| Check | Result |
|---|---|
| Driver / CUDA version (`nvidia-smi`) | |
| ctranslate2 CUDA device count & compute types | |
| Console engine line on startup | |
| B1 turbo: RTF mean / peak GPU MB / WER % | |
| B1 turbo beam 1: RTF / WER | |
| B1 large-v3: RTF / peak GPU / WER | |
| B1 distil-large-v3.5: RTF / WER | |
| B1 no prompt: WER | |
| B2 long 30 min: max queue / final latency / RSS start→end / max VRAM | |
| B2 misc + gui: all passed? worst UI gap | |
| B3 clipboard history hidden? auto-paste works in EMR? | |
| B3 Dragon vs MyTranscribe corrections (10 letters) | |
| Anything odd | |
