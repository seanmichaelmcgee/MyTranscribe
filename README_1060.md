# MyTranscribe Medical: GTX 1060 edition

A separate version of MyTranscribe for **long dictation (letters, notes) on older NVIDIA
cards**, built around a GTX 1060 6 GB. The original app (`src/gui_qt.py`, `run.bat`) is
unchanged and still works; this one lives alongside it.

| | Original (`gui_qt.py`) | Medical / 1060 (`gui_med.py`) |
|---|---|---|
| Engine | openai-whisper + PyTorch | faster-whisper (CTranslate2), **no PyTorch** |
| Default model on a 1060 | `large-v3` (does not fit in 6 GB) | `large-v3-turbo`, int8 weights (~1.6 GB VRAM) |
| When is audio transcribed? | All at once when you press Stop (window freezes) | In ~30 s pieces **while you talk**; Stop only waits for the last piece |
| Audio written to disk? | Yes, temp WAV files (may be left behind on Windows) | **Never**: kept in memory only |
| Transcript in the console log? | First 60 characters | **Never**: length only |
| Windows clipboard history / cloud sync | Keeps a copy | Each copy is marked "don't keep, don't sync" |
| Vocabulary hint | Programming terms | Medical letter (editable) |
| Long recordings | 3 min cap in Long mode | 1 hour per recording, either mode |
| Auto-paste into your app | No | Optional (`MYTRANSCRIBE_AUTOPASTE=1`) |

## Install (Windows)

Needs Python 3.11 and a CUDA-12-capable NVIDIA driver (any recent Game Ready or Studio
driver; the R580 branch is the last to support GTX 10-series cards).

```bat
cd C:\path\to\MyTranscribe
py -3.11 -m venv venv1060
venv1060\Scripts\python.exe -m pip install -r requirements-1060.txt
run_1060.bat
```

On the **first run** the model (~1.6 GB) is downloaded from Hugging Face into
`%USERPROFILE%\.cache\huggingface`. The window says "Loading speech model…" and the
buttons unlock when it's ready. After that, everything runs offline; set
`HF_HUB_OFFLINE=1` (see `run_1060.bat`) to guarantee nothing is contacted.

The console prints the chosen setup, e.g.
`Engine config: model=large-v3-turbo device=cuda compute=int8_float32 ... GPU NVIDIA GeForce GTX 1060 6GB (CC 6.1, 6144 MB): slow fp16`.
On a 1060 you want `device=cuda` and `compute=int8_float32`. If it says `device=cpu`,
see Troubleshooting.

## Use

Same controls as the original:

- **Ctrl+Alt+Q** from any app: start; press again to stop.
- **Space** (window focused): start/stop. **Start / Stop / Long Record** buttons.
- Text appears in the window as each ~30 s piece finishes. After Stop you'll see
  "[Finishing transcription…]" for a few seconds, then the full text is on the clipboard.

**Auto-paste mode** (`set MYTRANSCRIBE_AUTOPASTE=1` in `run_1060.bat`): click into your
EMR/Word field, press Ctrl+Alt+Q, dictate, press Ctrl+Alt+Q again. When transcription
finishes, the text is pasted where your cursor is. In this mode the hotkey does not
bring the MyTranscribe window to the front, so your cursor stays put. Stopping with the
on-screen button never auto-pastes (focus would be on MyTranscribe itself). Some
remote/Citrix EMRs block simulated keystrokes; if so, paste with Ctrl+V yourself.

**Always proofread** drug names, doses, laterality and numbers before signing.

## Make it learn your vocabulary

Edit `src/prompts/medical_prompt.txt`, or point `MYTRANSCRIBE_PROMPT_FILE` at your own
file. Whisper treats this as text that came *before* your audio, not as instructions,
so write it as a letter opening in your own style, full of the drug names, tests,
colleagues' names and abbreviations you use. Only the last ~150 words count, so keep it
short and put the most important terms near the end. Don't put real patient details in
it.

## Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `MYTRANSCRIBE_MODEL` | `large-v3-turbo` (GPU), `small.en` (CPU) | Any faster-whisper name (`large-v3`, `medium.en`, `distil-large-v3.5`…) or a local model folder |
| `MYTRANSCRIBE_COMPUTE_TYPE` | auto (`int8_float32` on Pascal) | CTranslate2 compute type |
| `MYTRANSCRIBE_DEVICE` | auto | `cpu` forces CPU |
| `MYTRANSCRIBE_BEAM_SIZE` | `5` | `1` is ~2x faster, slightly less accurate |
| `MYTRANSCRIBE_AUTOPASTE` | off | `1` = paste into the focused app after a hotkey stop |
| `MYTRANSCRIBE_PROMPT_FILE` | bundled medical prompt | Your vocabulary prompt |
| `HF_HUB_OFFLINE` | off | `1` = never contact Hugging Face (after first download) |

## Check speed on your machine

```bat
venv1060\Scripts\python.exe scripts\bench_engine.py --audio sample.wav
venv1060\Scripts\python.exe scripts\stress_pipeline.py --audio sample.wav --all
```

`sample.wav` must be 16 kHz mono (`ffmpeg -i in.m4a -ar 16000 -ac 1 -sample_fmt s16 sample.wav`).
Use a recording **without patient information**. See
[docs/STRESS_TEST_PLAN_1060.md](docs/STRESS_TEST_PLAN_1060.md) for the full checklist.

## Privacy checklist (your side)

The app keeps audio in memory and never logs transcript text, but the machine still
needs: BitLocker (full-disk encryption), a login password and auto-lock, and Windows
**Settings → System → Clipboard → Clipboard history: Off** and **Sync across devices:
Off** (belt and braces; the app already opts each copy out). This is not legal advice;
check with whoever handles privacy compliance for your practice.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Console says `device=cpu` / `CUDA probe failed` | Update the NVIDIA driver; confirm `nvidia-smi` works in a terminal; reinstall `nvidia-cublas-cu12` and `nvidia-cudnn-cu12` into `venv1060` |
| `Could not load library cudnn_ops64_9.dll` (or `cublas64_12.dll`) | Same as above; the app falls back to CPU automatically meanwhile |
| "Could not load the speech model" on first run | No internet for the one-time download, or `HF_HUB_OFFLINE=1` set too early |
| "Transcription is falling behind" warnings | Set `MYTRANSCRIBE_BEAM_SIZE=1`, or `MYTRANSCRIBE_MODEL=distil-large-v3.5` / `small.en` |
| Auto-paste does nothing in the EMR | Remote/Citrix session blocking simulated keys: use Ctrl+V |
| Words wrong at a ~30 s boundary | Report it: cuts are made at the quietest moment, but a long run-on sentence can still be split |

## Running the tests (developers)

```bash
pip install -r requirements-1060.txt
xvfb-run -a python -m pytest tests     # Linux headless; on Windows just: python -m pytest tests
```
