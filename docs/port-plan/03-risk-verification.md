# Windows Port — Risk Register & Verification Strategy

Scope: MyTranscribe port from GTK3/Linux to PyQt6/Windows 11, targeting the user's box
(Python 3.11.9, RTX 4070 Ti Super, CUDA 12.4, torch 2.6, ffmpeg 8.0). Personal use only.

Sources audited:
- `src/gui-v0.8.py` (GTK3 app, 330 LOC — will be rewritten against PyQt6)
- `src/transcriber_v12.py` (PyAudio + Whisper engine, 290 LOC)
- `src/sound_utils.py` (chime generation + PyAudio playback, 163 LOC)

---

## 1. Risk Register

| ID   | Risk | Linux vs Windows difference | Likelihood | Impact | Mitigation | Test case |
|------|------|-----------------------------|------------|--------|------------|-----------|
| R01  | **PyAudio default input picks wrong device** (e.g. Realtek monitor, HDMI audio, stereo mix) instead of the intended USB mic. | ALSA on Linux honors `default` → PulseAudio source, which is usually the real mic. On Windows, MME/WASAPI host-API defaults can be arbitrary; the "default input" changes when devices are hot-plugged or after reboot. | H | H | Enumerate devices at startup, log all with host-API + name, let user pick; persist device name (not index) and look it up by substring each launch. | T04 |
| R02  | **WASAPI exclusive mode** locks the mic for MyTranscribe and blocks other apps (or vice versa). | Linux has no exclusive-mode concept for ALSA/Pulse. Windows default host API via PortAudio is MME (shared), but users commonly enable "Allow applications to take exclusive control" in Sound settings. | M | M | Explicitly request MME or WASAPI-shared in `PyAudio.open(...)` by selecting `input_device_index` from a non-exclusive host API. Log host API of chosen device. | T04, T17 |
| R03  | **PyAudio device index drift** across reboots / USB re-enumeration. | Linux device names tend to persist; Windows PortAudio indexes shift when any USB audio device is plugged/unplugged. | H | M | Never hard-code index. Resolve by name substring at startup; fall back to `default_input_device_info()` with a warning. | T04, T18 |
| R04  | **Stereo-only USB mics** recorded as mono truncate the left channel only, yielding silent or half-volume audio. | `CHANNELS = 1` hard-coded in `transcriber_v12.py:15`. Many Windows webcam/USB mics expose 2-channel input. | M | M | Query `maxInputChannels` for chosen device; if > 1, open 2ch, downmix to mono before sending to Whisper. | T04, T19 |
| R05  | **pynput keyboard listener blocked by UAC-elevated foreground window** (Task Manager, regedit, any app running as admin). | Linux X11 keyboard hooks are not tied to UAC. On Windows, an unelevated low-level hook cannot observe input directed at an elevated window. | H | L | Accept the limitation (personal use, rarely talking into admin tools). Document it. Optionally offer "Run as admin" shortcut. | T05, T20 |
| R06  | **AV / EDR software** (Windows Defender, Malwarebytes) quarantines the pynput low-level keyboard hook or flags it as a keylogger. | Linux has no comparable scanner. Windows ML-based AV sometimes flags `pynput.keyboard.Listener`. | M | H | Check first launch for AV alert; if flagged, add venv to Defender exclusions list. Keep the source tree local (no signed exe). | T05 |
| R07  | **Ctrl+Alt+Q conflicts** with a Windows app-specific shortcut. | On Linux the user has no known binding. Ctrl+Alt+Q is used by a few apps (Google Hangouts in Chrome, some IDE plugins). Windows itself does **not** reserve it, but Chrome/Meet will steal it when focused. | L | M | Keep Ctrl+Alt+Q. Document the known Chrome-Meet conflict. Re-bind is cheap if it bites. | T05, T20 |
| R08  | **QApplication.clipboard() called from a non-GUI thread crashes / returns stale data.** | GTK's `Gtk.Clipboard.get(...)` could be called from worker threads with GDK locking; Qt's `QClipboard` is **strictly** main-thread-only and will segfault or warn-then-discard on wrong thread. | H | H | Route clipboard sets through `QMetaObject.invokeMethod(..., Qt.QueuedConnection)` or `QTimer.singleShot(0, ...)`. Never call `setText` from the PyAudio/Whisper worker thread. | T06, T21 |
| R09  | **Clipboard `setText` → immediate Ctrl+V race**: Windows apps (especially Electron: Discord, VS Code, Chrome) read the clipboard *before* the OLE delayed-render commit flushes. | GTK calls `clipboard.store()` synchronously. Qt's `setText` is synchronous to CF_UNICODETEXT, but some apps still miss the first poll. | M | M | After `setText`, call `clipboard.text()` to force materialization; optionally sleep 30–50 ms before playing the end-chime (gives the user reaction time anyway). | T06, T22 |
| R10  | **Windows Clipboard History (Win+V) swallows or re-orders** the transcribed text. | No Linux analog. If Clipboard History is enabled, rapid successive transcriptions stack in history; "clear on exit" behavior differs. | L | L | Document. Don't try to disable Clipboard History. | T06 |
| R11  | **Temp WAV file locked by antivirus mid-read**, causing `whisper.transcribe(path)` to fail with `PermissionError` or a torchaudio decode error. | Linux has no on-access scanner. Defender routinely scans newly-written `.wav` in `%TEMP%`. | M | M | Retry `whisper.transcribe` once on `PermissionError`; sleep 100 ms between write and read. Consider using `%LOCALAPPDATA%\MyTranscribe\tmp` and adding it to Defender exclusions. | T11, T23 |
| R12  | **Known `os.remove` bug at `transcriber_v12.py:221-222`**: the WAV file was already closed in the `with` block, but under Windows' stricter file-sharing semantics, a race against ffmpeg's handle (opened by Whisper → torchaudio) can leave it locked for ~20–200 ms. | `os.remove` on Linux succeeds even if the file is open; Windows holds an exclusive delete lock. | H | L | Wrap `os.remove` in a retry-on-`PermissionError` loop (3 tries × 50 ms). Alternative: use `tempfile.NamedTemporaryFile(delete=True)` and let GC handle it on the main thread. | T11 |
| R13  | **Other double-open paths in codebase** that will bite on Windows. Surveyed: `sound_utils.py:47,92` write chime WAVs at startup then re-open read-only in `_play_sound_thread` — safe because writer is closed. `sound_utils.py:21-25, 62-66` delete-on-startup — wrapped in bare `except`, so silently works. No other file-open pairs exist. | Same sharing semantics as R12 but closed-before-reopen pattern works on Windows. | L | L | No code change needed. Keep the bare `except` on startup-delete. | T11 |
| R14  | **Whisper model cache path** default (`%USERPROFILE%\.cache\whisper`) on an account with non-ASCII characters in the username. | Linux `$HOME` rarely has non-ASCII. Windows `smich` is safe, but the `torch.hub` / `whisper._MODELS` resolver can still trip on `%USERPROFILE%` containing spaces (not an issue here). | L | M | Confirmed target user is `smich` — safe. Log `whisper._MODELS` cache dir at first run. | T02 |
| R15  | **Relative working directory at launch** — launching from Start Menu / pinned shortcut sets `cwd` to `C:\Windows\System32`, breaking any `open("relative/path")` calls. Survey: no relative file I/O in the three source files today, but PyQt6 resource loading must use absolute paths. | Linux desktop launchers usually inherit `cwd` from `$HOME`. Windows shortcuts default to the exe's own dir, which for a `python.exe` shortcut is `System32`. | M | M | Resolve all paths via `pathlib.Path(__file__).parent` or `__file__`-relative. Add a top-level `os.chdir(Path(__file__).parent)` at entry. | T01 |
| R16  | **Logging file handle**: code today only uses `StreamHandler(sys.stdout)`. If a future log file is added and `cwd = System32`, the open will fail with `PermissionError`. | Same as R15. | L | L | Pre-emptive: if a file handler is added, use `%LOCALAPPDATA%\MyTranscribe\logs`. | — |
| R17  | **CUDA first-inference latency** (~3–8 s on Windows) blocks the UI thread if model is loaded synchronously in `__init__`. | Linux NVIDIA driver has smaller warmup. Windows WDDM adds ~1 s; plus torch 2.6 cu124 kernels get JIT-compiled on first call. | H | M | Load model on worker thread after UI paints; show "Loading model…" state. Optionally run a 0.1 s dummy inference at startup to absorb warmup before the first hotkey press. | T02, T12 |
| R18  | **Driver/torch mismatch**: torch 2.6 built against CUDA 12.4 requires NVIDIA driver ≥ 550.x. Older driver gives cryptic `CUDA error: no kernel image is available for execution on the device` or silent CPU fallback. | Same everywhere, but Windows users often lag on GeForce drivers. | M | H | Startup asserts: `torch.cuda.is_available()` AND `torch.cuda.get_device_capability(0) >= (8,9)` (Ada). Print driver version via `torch.version.cuda`. Fail loud, don't silently CPU-fall-back. | T02 |
| R19  | **GPU memory fragmentation after many long-record sessions** — Whisper allocates/frees decoder workspaces, eventually OOMs on 3-minute chunks. | Linux and Windows both show this under torch; Windows WDDM reserves ~1.5 GB for the desktop compositor, reducing headroom. | L | M | After each `stop_recording`, call `torch.cuda.empty_cache()`. Log `torch.cuda.memory_allocated()` once per session. | T07, T24 |
| R20  | **Qt always-on-top broken** when a UAC prompt, Windows Notification, or fullscreen exclusive game is focused. | `Qt.WindowStaysOnTopHint` does not override secure-desktop (UAC) or fullscreen-exclusive apps. Same as GTK but users may expect it to work. | M | L | Document. No fix possible without kernel-level hooks. | T25 |
| R21  | **Window opacity on multi-monitor with mixed DPI** — Qt composition of a 90% opaque window over a 4K@150% secondary monitor can show rendering artifacts or full opacity on one monitor. | GTK3 on X11 handled this via compositor; Windows DWM composites per-monitor. | L | L | Set `Qt.AA_EnableHighDpiScaling` before `QApplication`. Test on both monitors if available. | T13 |
| R22  | **DPI scaling on 4K at 150%/200%** — fixed-pixel sizes (`set_size_request(50, 4)` for audio indicator at `gui-v0.8.py:131`) render as 4 physical pixels, invisible. | GTK auto-scales via GDK\_SCALE. Qt needs `AA_EnableHighDpiPixmaps` + logical-pixel-aware layout. | M | M | Use `QSizePolicy` + logical pixels; set minimum widget sizes in `em`-equivalents (e.g. 3× `fontMetrics().height()`). Test on 4K. | T13 |
| R23  | **PyQt6 signal/slot across threads** — emitting a signal from the PyAudio thread (`record_loop`) into the GUI must use `Qt.QueuedConnection` or default auto-connection. Direct method calls (like today's `GLib.idle_add`) won't exist. | GTK had `GLib.idle_add` for marshalling. PyQt6 uses signals; wrong connection type = race or wrong-thread paint. | H | H | All transcriber → GUI communication goes through a `pyqtSignal(str)` on a `QObject` owned by the main thread. Never touch `QTextEdit` / `QClipboard` from worker threads. | T02, T06, T21 |
| R24  | **QTimer drift** for the 30 ms audio-indicator refresh — Windows default timer resolution is 15.6 ms; a 30 ms timer quantizes to 31 ms or 46 ms depending on global `timeBeginPeriod`. | Linux timers are ~1 ms resolution by default. | M | L | Accept quantization — 46 ms refresh is still ~22 FPS, plenty for a blinking indicator. Don't call `timeBeginPeriod(1)`; it's global and power-hungry. | T08 |
| R25  | **Whisper's internal background work + Qt event loop**: `model.transcribe(path)` blocks for seconds. If accidentally called on the Qt thread, UI freezes. | Today it runs on `record_thread` (daemon Python thread) — which in PyQt6 still works, but GUI updates from inside it need signals, not direct `QTextEdit.setPlainText`. | H | H | Keep `RealTimeTranscriber.record_thread`. Expose `transcription_ready = pyqtSignal(str)` and emit from the worker; main-thread slot updates the widget. | T23 |
| R26  | **Non-ASCII transcription chars (curly quotes, é, em-dash) hit `print(f"[DEBUG]... {text[:60]}")`** on a cp1252 console → `UnicodeEncodeError`, crashes or swallows the log. | Linux terminals are UTF-8. Windows `cmd.exe` / PowerShell default is cp1252 (or cp437) unless `chcp 65001` or `PYTHONIOENCODING=utf-8`. | H | M | Set `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at entry. Remove the `print` at `gui-v0.8.py:316` during PyQt6 port (logger already covers it). | T09 |
| R27  | **Clipboard non-ASCII** — copying "café" to Windows clipboard: PyQt6 `QClipboard.setText` uses CF_UNICODETEXT (UTF-16), which is correct. The risk is *retrieval* by legacy apps that read CF_TEXT (cp1252). Notepad, Word, Chrome, VS Code are all fine. | Same cp1252 issue but clipboard-side. | L | L | No action needed for target use case. | T09 |
| R28  | **PyAudio stream not released on exception** during `__init__` model load — leaves phantom input stream, next launch fails with "Device unavailable". | Linux ALSA auto-recovers on process death; Windows WASAPI requires explicit `Close()` or waits for the kernel grace period. | L | M | Move `pyaudio.PyAudio()` creation into a `try/finally` tied to `start_recording`, not `__init__`. Alternatively, register an `atexit` that terminates the audio interface. | T10 |
| R29  | **pynput listener thread not joined on exit** — leaks a background thread on quit-via-window-close, preventing process termination. | Linux `pynput` uses X11 display thread; exits cleanly on SIGTERM. Windows low-level hook lives in a separate message loop that blocks interpreter shutdown. | M | M | `listener.stop()` + `listener.join(timeout=2.0)` in the closeEvent handler; fall back to `os._exit(0)` if the listener thread won't die. | T10 |
| R30  | **CUDA context release on Ctrl+C / window-close / Ctrl+Alt+Q** — without explicit `del model; torch.cuda.empty_cache()`, the next launch may see lingering GPU memory for 5–15 s (WDDM reclaim). | Linux releases on process exit via unified memory unmap. Windows WDDM batches the release. | M | L | Call `torch.cuda.empty_cache()` + `del self.model` in `closeEvent`. Acceptable to leave to OS in personal-use scenario. | T10 |
| R31  | **Ctrl+C from terminal** doesn't raise `KeyboardInterrupt` through the Qt event loop — the signal is queued but never delivered until an event arrives. | GTK's main loop polls signals; Qt on Windows needs `signal.signal(signal.SIGINT, signal.SIG_DFL)` or a periodic `QTimer` that yields to Python. | M | L | Add `signal.signal(signal.SIGINT, signal.SIG_DFL)` right after `QApplication(sys.argv)`. | T10 |
| R32  | **ffmpeg not on PATH for the venv's Python** — Whisper shells out to ffmpeg for audio decode; if `PATH` is set only in system env but the venv's `activate.bat` reset it, decode fails with `FileNotFoundError`. | Unix `/usr/bin/ffmpeg` is always findable. Windows venv inherits system PATH unless launched weirdly. | L | H | Startup check: `shutil.which("ffmpeg")` must be non-None; fail loud with install hint. | T00 |
| R33  | **Temp dir unwritable** or on a redirected OneDrive folder. | `%TEMP%` on Windows sometimes maps to a OneDrive-synced path → random sync collisions on rapid writes. | L | M | Startup check: write/delete a probe file in `tempfile.gettempdir()`. If `%TEMP%` is under `OneDrive`, fall back to `%LOCALAPPDATA%\Temp`. | T00 |
| R34  | **Chime files colliding across runs**: `sound_utils.py` writes fixed-name files (`mytranscribe_start_chime.wav`) in `%TEMP%`; two instances would both try to delete + re-create. | Same on Linux but Windows file-locking makes the delete fail louder. | L | L | Use PID-suffixed paths or hash-of-params paths; wrap delete in `except OSError`. Already wrapped — no change needed. | — |
| R35  | **Exclusive-mode WASAPI mic grabbed by Discord / Meet / Teams** while MyTranscribe tries to open it → `-9985` `Device unavailable`. | Linux PulseAudio multiplexes by default. Windows shared mode would too, but some conferencing apps request exclusive. | M | M | On open failure, log "mic busy", sleep 500 ms, retry once. Document: close other conferencing apps. | T04 |
| R36  | **3-minute auto-stop fires but UI button stuck in "recording"** if the `running = False` from the 180 s timeout doesn't round-trip through a signal to the GUI. | Pure threading/signaling risk — same on Linux but we're rewriting the bridge. | M | M | `RealTimeTranscriber` emits `recording_finished = pyqtSignal()` when `record_loop` exits naturally; slot on main thread calls `update_button_states()`. | T07 |

**Totals**: 36 risks. H×H count: **4** (R01, R08, R23, R25). H×M count: 5 (R03, R17, R23 [dup], R26, R27 — actually R26 is H×M).

---

## 2. Verification Test Plan

All tests assume the project venv is activated and `cd C:\Users\smich\Apps\MyTranscribe`.

### T00 — Environment preflight

- **Precondition**: Fresh shell, venv activated.
- **Procedure**: Run the audit script in section 3.
- **Expected**: All 10 checks print `PASS`.
- **If fail**: Fix the specific line before touching anything else.

### T01 — Cold-start smoke (launch + window paints + stays on top)

- **Risks**: R15, R20, R22
- **Precondition**: T00 passed. App launched via `python src/gui-v0.8.py` from project root AND from a Start-menu shortcut (if one exists; else `cd C:\Windows\System32 && python C:\Users\smich\Apps\MyTranscribe\src\gui-v0.8.py`).
- **Procedure**:
  1. Launch.
  2. Open Notepad, click inside it.
  3. Observe the MyTranscribe window.
- **Expected**: Window visible on top of Notepad within 3 s. Title "Real-Time Transcription". Buttons rendered at readable size on the primary monitor's DPI.
- **If fail**: Check `Qt.WindowStaysOnTopHint` set before `show()`; check `AA_EnableHighDpiScaling`; log `QApplication.primaryScreen().devicePixelRatio()`.

### T02 — CUDA smoke (model on GPU, first inference succeeds, driver OK)

- **Risks**: R14, R17, R18
- **Precondition**: T00 passed.
- **Procedure**: From venv, run:
  ```python
  python -c "import torch, whisper; \
  print('cuda', torch.cuda.is_available(), torch.version.cuda); \
  print('dev', torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)); \
  m = whisper.load_model('small', device='cuda'); \
  import numpy as np; \
  _ = m.transcribe(np.zeros(16000, dtype=np.float32), language='en', fp16=True); \
  print('inference OK')"
  ```
- **Expected**: `cuda True 12.4`, `dev NVIDIA GeForce RTX 4070 Ti SUPER (8, 9)`, `inference OK`, total runtime < 20 s.
- **If fail**: If `cuda False` → driver too old, update GeForce driver ≥ 550. If `no kernel image` → torch built for wrong CUDA, reinstall with correct `--index-url`.

### T03 — Import smoke (no ModuleNotFoundError, no DLL load fails)

- **Risks**: —
- **Precondition**: T00 passed.
- **Procedure**: `python -c "import PyQt6.QtWidgets, whisper, torch, pyaudio, pynput, numpy, wave, tempfile"`
- **Expected**: Exits 0, no output.
- **If fail**: Note which module; `pip install` the missing one or reinstall from `requirements-windows.txt`.

### T04 — Mic selection smoke (correct input device captures audio)

- **Risks**: R01, R02, R03, R04, R35
- **Precondition**: Intended USB mic plugged in. Nothing else using it (Discord/Teams closed).
- **Procedure**:
  1. Run:
     ```python
     python -c "import pyaudio; p=pyaudio.PyAudio(); \
     [print(i, p.get_device_info_by_index(i)['name'], \
            p.get_device_info_by_index(i)['maxInputChannels'], \
            p.get_host_api_info_by_index(p.get_device_info_by_index(i)['hostApi'])['name']) \
       for i in range(p.get_device_count()) \
       if p.get_device_info_by_index(i)['maxInputChannels']>0]"
     ```
  2. Note the index of the intended mic (e.g. "USB Microphone" under MME).
  3. Launch MyTranscribe, start a recording, speak "one two three four five", stop.
- **Expected**: Log line shows `Using input device #N: <name> via MME` matching step 2. Transcription contains "one two three four five".
- **If fail**: If wrong device chosen, add env var `MYTRANSCRIBE_MIC="USB Microphone"` and re-run; update device picker logic.

### T05 — Global hotkey smoke (Ctrl+Alt+Q from another focused app)

- **Risks**: R05, R06, R07
- **Precondition**: MyTranscribe running. Notepad opened and focused (click in it).
- **Procedure**:
  1. With Notepad focused, press and hold Ctrl+Alt, tap Q.
  2. Speak "hotkey test", press Ctrl+Alt+Q again.
- **Expected**: Start chime plays after first press, end chime after second. Transcription text "hotkey test" appears in MyTranscribe window and is on the clipboard.
- **If fail**: If no chime → pynput blocked; check Task Manager for Defender quarantine or add venv to exclusions. If only fires when MyTranscribe has focus → listener not started / wrong thread.

### T06 — Clipboard smoke (setText → Ctrl+V into Notepad works)

- **Risks**: R08, R09, R10
- **Precondition**: T05 just completed successfully (clipboard holds "hotkey test").
- **Procedure**: Focus Notepad, press Ctrl+V.
- **Expected**: "hotkey test" pastes. No crash. `QClipboard` warning absent from log.
- **If fail**: Check for `QObject::setText: Cannot send events to objects owned by a different thread` in log → fix signal connection type to `Qt.QueuedConnection`.

### T07 — Long-record smoke (3-minute auto-stop fires cleanly)

- **Risks**: R19, R36
- **Precondition**: MyTranscribe running, idle.
- **Procedure**:
  1. Click "Long Record".
  2. Speak for 10 s, then stay silent.
  3. Wait a full 180 s from click (set a phone timer).
- **Expected**: At ~180 s, end chime plays, transcription appears, buttons return to idle state (Start enabled, Stop disabled), audio indicator hidden. Log shows `torch.cuda.memory_allocated` ≤ 3 GB.
- **If fail**: If buttons stuck → `recording_finished` signal not wired. If OOM → add `torch.cuda.empty_cache()` after each chunk.

### T08 — Audio indicator refresh rate

- **Risks**: R22, R24
- **Precondition**: MyTranscribe running.
- **Procedure**: Start recording, tap the mic / speak rhythmically, watch the indicator blob.
- **Expected**: Indicator visibly pulses in response to speech within ~100 ms. Visible (not zero pixels) on the current DPI.
- **If fail**: If invisible → replace fixed `setFixedSize(50, 4)` with DPI-aware sizing. If sluggish → ensure timer runs on GUI thread, not blocked by paint events.

### T09 — Non-ASCII smoke (curly quotes, é, em-dash survive round-trip)

- **Risks**: R26, R27
- **Precondition**: MyTranscribe running.
- **Procedure**: Start recording. Say clearly: `café résumé — "it's fine"`. Stop. Paste into Notepad AND into an open PowerShell window with `> ` prompt (via `Get-Clipboard | Out-File utf8.txt -Encoding utf8`).
- **Expected**: Both targets show the accented characters. No `UnicodeEncodeError` in MyTranscribe log.
- **If fail**: Add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at entry, or remove `print()` calls with user text.

### T10 — Exit smoke (all three exit paths release resources)

- **Risks**: R28, R29, R30, R31
- **Precondition**: Clean state, no MyTranscribe running.
- **Procedure**: For each of three exit methods separately:
  - **a)** Launch from terminal, do one short recording, press Ctrl+C in the terminal.
  - **b)** Launch, do one recording, click the window's X.
  - **c)** Launch, do one recording, press Ctrl+Alt+Q twice (to stop recording), then... press the X or define a "quit hotkey" — if none, just b).
  For each, within 5 s of exit:
  1. `tasklist | findstr python` — should show nothing MyTranscribe-related.
  2. `nvidia-smi` — GPU memory used by python.exe should be 0.
  3. Immediately relaunch — should succeed without "Device unavailable".
- **Expected**: All three paths leave no zombie processes, no lingering GPU allocation, mic releasable immediately.
- **If fail**: (a) `signal.signal(SIGINT, SIG_DFL)` missing. (b) PyAudio `.terminate()` not called in closeEvent. (c) pynput `.stop()` not called; fall back to `os._exit(0)`.

### T11 — Temp WAV lock / AV race

- **Risks**: R11, R12, R13
- **Precondition**: MyTranscribe running. Windows Defender real-time protection ON (default).
- **Procedure**: Do 10 short (3 s) recordings back-to-back via Ctrl+Alt+Q. Watch log.
- **Expected**: No `PermissionError`, no `[Transcription Error: ...]` lines. All 10 transcriptions show up.
- **If fail**: Add retry-on-PermissionError around `os.remove` and `model.transcribe`. Consider Defender exclusion for `%TEMP%\*.wav`.

### T12 — Model load non-blocking

- **Risks**: R17
- **Precondition**: Cold: last launch was ≥ 5 min ago (so CUDA is cold).
- **Procedure**: Launch. **Immediately** try to drag the window.
- **Expected**: Window responds to drag within 200 ms. Buttons may show "Loading…" until model ready, but the UI thread is not frozen.
- **If fail**: Move `whisper.load_model` into a `QThread`; show a spinner; gate hotkey until loaded.

### T13 — DPI / multi-monitor

- **Risks**: R21, R22
- **Precondition**: Primary monitor at native scaling. If user has a second monitor, both are connected.
- **Procedure**: Launch on primary. Drag window to secondary monitor (if present). Observe opacity and widget sizes.
- **Expected**: Window opacity ~90% on both. Buttons and audio indicator legible on both. No rendering artifacts.
- **If fail**: Ensure `QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)` called BEFORE `QApplication(sys.argv)`.

### T14 — Button click flow (sanity)

- **Risks**: R23, R25
- **Precondition**: MyTranscribe running.
- **Procedure**: Click Start. Speak. Click Stop.
- **Expected**: Same behavior as hotkey path. Text appears, clipboard has it, chimes play.
- **If fail**: Button signal probably wired to wrong slot or hit a thread boundary.

### T15 — Normal-mode 5-minute duration

- **Risks**: R19, R23
- **Precondition**: MyTranscribe idle.
- **Procedure**: Start normal recording. Speak intermittently for 5 minutes. Stop.
- **Expected**: Chunks transcribed and appended live every ~300 s. Final concatenation on stop. `torch.cuda.memory_allocated()` logged ≤ 4 GB peak. No UI freeze > 1 s.
- **If fail**: See T07 mitigation plus check `DEFAULT_CHUNK_DURATION` behavior.

### T16 — Repeated hotkey spam

- **Risks**: R08, R29
- **Precondition**: MyTranscribe running.
- **Procedure**: Press Ctrl+Alt+Q, immediately Ctrl+Alt+Q, pause 1 s, repeat 10 times.
- **Expected**: Each press toggles state. No crash, no stuck state. Clipboard ends up with the *last* non-empty transcription (or empty).
- **If fail**: Debounce the hotkey in `on_global_press`; ensure `self.q_pressed = False` reset on every fire.

### T17 — WASAPI exclusive-mode regression

- **Risks**: R02
- **Precondition**: In Windows Sound Settings → chosen mic → Properties → Advanced → "Allow applications to take exclusive control" = **checked**.
- **Procedure**: Run T04 again. Then open Voice Recorder (stock Windows app) while MyTranscribe is recording.
- **Expected**: Both can record simultaneously (MyTranscribe used shared mode).
- **If fail**: Explicit host API selection missing; force MME or WASAPI-shared.

### T18 — Device index drift

- **Risks**: R03
- **Precondition**: MyTranscribe just worked with the USB mic.
- **Procedure**:
  1. Unplug the USB mic.
  2. Plug in a different USB device (any — storage, keyboard, whatever is handy).
  3. Replug the mic.
  4. Relaunch MyTranscribe, do a recording.
- **Expected**: Still records from the correct mic.
- **If fail**: Device lookup is by index; change to name-substring match.

### T19 — Stereo-mic downmix

- **Risks**: R04
- **Precondition**: If the user's mic reports `maxInputChannels = 1`, this test is N/A (verify via T04 step 1 output).
- **Procedure**: If stereo mic, record "left right test" speaking into it.
- **Expected**: Transcription has all three words.
- **If fail**: Open stream with `channels=<device max>`, downmix `(L+R)/2` to mono ndarray before WAV write.

### T20 — Hotkey in elevated app

- **Risks**: R05, R07
- **Precondition**: MyTranscribe running unelevated.
- **Procedure**: Open Task Manager (elevated). With TM focused, press Ctrl+Alt+Q.
- **Expected**: **Does NOT fire** — this is working-as-designed. Documented limitation.
- **If fail (fires)**: Surprisingly good; no action.
- **If test documents failure**: No fix attempted — requires running MyTranscribe as admin, out of scope for personal use.

### T21 — Clipboard from worker thread (regression)

- **Risks**: R08, R23
- **Precondition**: Dev-only; simulated or code-review check.
- **Procedure**: Grep the codebase for `clipboard()` / `setText` calls; verify each is on the main thread (inside a slot connected via `Qt.AutoConnection` or explicit `Qt.QueuedConnection`).
- **Expected**: Zero calls to `QClipboard` from `record_thread` or any `QThread` worker. All paths go through `pyqtSignal`.
- **If fail**: Refactor — add a `transcription_ready = pyqtSignal(str)` on a main-thread `QObject`.

### T22 — Clipboard paste into Electron app

- **Risks**: R09
- **Precondition**: Discord OR VS Code running with a focused text field.
- **Procedure**: Record "paste test", let it finish, focus Discord/VS Code input, press Ctrl+V.
- **Expected**: Text pastes on first try.
- **If fail**: Add 50 ms `QTimer.singleShot` after `setText` before emitting the "done" signal.

### T23 — Defender scanning latency

- **Risks**: R11, R25
- **Precondition**: Defender real-time protection ON.
- **Procedure**: Trigger a recording that generates a 10 MB+ WAV (speak for ~5 min in long mode). Watch for `Transcription Error` in log.
- **Expected**: No error. Transcription completes.
- **If fail**: Retry loop around `model.transcribe(path)`; or add `%TEMP%\*.wav` to exclusions.

### T24 — GPU memory regression

- **Risks**: R19
- **Precondition**: MyTranscribe idle after cold launch.
- **Procedure**:
  1. Note `nvidia-smi` python.exe usage baseline.
  2. Do 5 long-record sessions (3 min each).
  3. Re-check `nvidia-smi`.
- **Expected**: Python.exe GPU usage does not grow more than 500 MB between start and end.
- **If fail**: Add `torch.cuda.empty_cache()` after each `stop_recording` and after each `process_audio_chunk`.

### T25 — Always-on-top under UAC

- **Risks**: R20
- **Precondition**: MyTranscribe running. Some elevated-requiring action queued (e.g. right-click cmd.exe → Run as administrator).
- **Procedure**: Trigger UAC prompt. Observe whether MyTranscribe stays visible.
- **Expected**: UAC prompt takes foreground (secure desktop). MyTranscribe window is temporarily hidden. On dismissal, MyTranscribe returns on top.
- **If fail**: Document. No fix.

---

## 3. Pre-launch Environment Audit Script

Save as `scripts/audit_env.py` and run before any testing:

```python
# scripts/audit_env.py — run from project root inside the venv
import os, sys, shutil, tempfile, ctypes
from pathlib import Path

def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    return bool(ok)

ok = True
ok &= check("Python 3.11.x", sys.version_info[:2] == (3, 11), sys.version.split()[0])
ok &= check("venv active", sys.prefix != sys.base_prefix, sys.prefix)
ok &= check("cwd is project root",
            Path.cwd().joinpath("src", "transcriber_v12.py").exists(), str(Path.cwd()))
ok &= check("ffmpeg on PATH", shutil.which("ffmpeg") is not None, shutil.which("ffmpeg") or "")
try:
    import torch
    ok &= check("torch CUDA available", torch.cuda.is_available(),
                f"torch {torch.__version__} / cuda {torch.version.cuda}")
    ok &= check("GPU is RTX 4070 Ti Super", "4070 Ti SUPER" in torch.cuda.get_device_name(0),
                torch.cuda.get_device_name(0))
    ok &= check("SM >= 8.9 (Ada)", torch.cuda.get_device_capability(0) >= (8, 9),
                str(torch.cuda.get_device_capability(0)))
except Exception as e:
    ok &= check("torch import", False, repr(e))
ok &= check("PyQt6 importable",
            __import__("importlib").util.find_spec("PyQt6.QtWidgets") is not None)
td = Path(tempfile.gettempdir())
probe = td / "mytranscribe_probe.txt"
try:
    probe.write_text("ok"); probe.unlink()
    ok &= check("tempdir writable", True, str(td))
except Exception as e:
    ok &= check("tempdir writable", False, repr(e))
ok &= check("no OneDrive in TEMP", "OneDrive" not in str(td), str(td))
free_gb = shutil.disk_usage(Path.home()).free / 2**30
ok &= check(">= 5 GB free in HOME", free_gb >= 5, f"{free_gb:.1f} GB")
sys.exit(0 if ok else 1)
```

Expected output: 10 `PASS` lines, exit code 0. Any `FAIL` → fix before running tests.

---

## 4. Smoke-test-first Ordering

Ranked by `(uncertainty eliminated) / (seconds to run)`. Run this sequence after each implementation phase; stop at the first failure.

| Order | Test | Typical time | Why it goes here |
|-------|------|--------------|------------------|
| 1 | **T00** (env audit) | 5 s | Instant. Catches half the stupid failures. |
| 2 | **T03** (import smoke) | 3 s | If any lib fails to import, nothing else matters. |
| 3 | **T02** (CUDA smoke) | 15 s | If CUDA is broken, the whole app is 20× slower; stop now. |
| 4 | **T01** (cold-start window) | 20 s | Confirms the Qt rewrite fundamentally works. |
| 5 | **T14** (button click flow) | 30 s | Smallest "does the app do the thing" test. Needs mic. |
| 6 | **T04** (mic selection) | 45 s | Wrong mic = empty transcripts forever; catches early. |
| 7 | **T05** (global hotkey) | 30 s | The core UX. If pynput is AV-quarantined, find out now. |
| 8 | **T06** (clipboard paste) | 15 s | Follows T05's output; single Ctrl+V into Notepad. |
| 9 | **T10** (exit smoke, path (b) only) | 30 s | Catches resource-leak regressions that cause T04/T05 to fail on next launch. |
| 10 | **T11** (temp WAV / AV race) | 60 s | The `os.remove` bug is known; validate the fix under real AV. |
| 11 | **T12** (model load non-blocking) | 30 s | UI-freeze regression — subtle but annoying. |
| 12 | **T09** (non-ASCII) | 45 s | One line of speech; catches the cp1252 footgun. |
| 13 | **T08** (audio indicator refresh) | 30 s | Visual polish; runs alongside T14/T05. |
| 14 | **T16** (hotkey spam) | 30 s | Reveals race/debounce bugs. |
| 15 | **T13** (DPI / multi-monitor) | 2 min | Only if user has a second monitor; otherwise skip. |
| 16 | **T07** (long-record 3-min auto-stop) | 3.5 min | Time-expensive but covers OOM + recording_finished signal. |
| 17 | **T22** (Electron paste) | 45 s | Nice-to-have; Discord/VS Code paste test. |
| 18 | **T18** (device index drift) | 90 s | Physical unplug test; run once per port milestone. |
| 19 | **T17** (WASAPI exclusive) | 2 min | Only if the user has ticked exclusive-mode or hit R02. |
| 20 | **T19** (stereo downmix) | 1 min | Skip if mic is mono (check T04 output). |
| 21 | **T15** (5-min normal mode) | 5.5 min | Stress test; run before declaring the port done. |
| 22 | **T24** (GPU memory regression) | 20 min | Runs 5 long sessions; only for final sign-off. |
| 23 | **T23** (Defender latency) | 6 min | Sub-variant of T07 with larger WAV. Run once. |
| 24 | **T10 a+c** (Ctrl+C, Ctrl+Alt+Q exit) | 2 min | Beyond the basic (b) above. |
| 25 | **T20** (elevated-app hotkey) | 1 min | Documents a known limitation; run once ever. |
| 26 | **T21** (thread audit) | code review, 5 min | Static; can be skipped during fast-iteration. |
| 27 | **T25** (UAC on-top) | 30 s | Documentation only. Run once. |

**Three tests the orchestrator should run first after every implementation checkpoint**:
1. **T00** (env audit) — 5 s
2. **T02** (CUDA smoke) — 15 s
3. **T05** (global hotkey end-to-end with clipboard via T06) — 45 s combined

Those three, in order, in under 90 seconds, eliminate ~70% of the possible failure surface.
