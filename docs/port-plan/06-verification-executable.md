# MyTranscribe Windows Port — Executable Verification Runbook

Source of truth: `docs/port-plan/03-risk-verification.md` (26 test cases T00–T25,
risk register R01–R36, audit script outline §3).

All commands assume:
- Working directory: `C:\Users\smich\Apps\MyTranscribe`
- Venv activated: `.\venv\Scripts\activate`
- Shell: Git Bash or PowerShell (commands shown for Git Bash unless noted)

---

## A. How to use this document

Run the tests in the order listed for each phase. The sequence is designed
so that the cheapest, most diagnostic test runs first. **Stop at the first
failure** — it identifies the layer that broke. Fix it, re-run the stopping
test, then continue forward.

Tests marked **[NEEDS gui_qt.py]** cannot be run before Phase 3 completes
(`src/gui_qt.py` does not exist yet). Run those tests with the command
shown; if the file is missing, the command will print `No module named` or
`No such file` — that is the expected pre-Phase-3 result.

Tests marked **HUMAN:** require visual observation and cannot be automated.

---

## B. Phase-to-test mapping

| Phase | Tests to run (in order) | Stop if |
|---|---|---|
| Phase 0 (env snapshot) | `python scripts/audit.py`, T00, T03 | audit exits non-zero OR T03 import fails |
| Phase 1 (transcriber hardening) | T00, T03, T11 (tempfile/AV race) | T00 fails (env changed) OR T11 shows PermissionError |
| Phase 2 (PyQt6 scaffold) | T00, T03, T01 (window paints, always-on-top, opacity) | T01: window does not appear or is not on top |
| Phase 3 (feature-parity rewrite) | T00, T03, T02, T01, T14, T04, T06, T08, T09, T12, T15 | first failure in sequence |
| Phase 4 (global hotkey) | T05, T06, T16, T20, T21 (code review) | T05: hotkey does not trigger OR T06: clipboard not pasted |
| Phase 5 (full E2E) | T00–T25 (all 26, ordered per §4 of risk doc) | first failure; document any known-limitation passes |

---

## C. Quick-pass suite

From `docs/port-plan/03-risk-verification.md` §4 ("Three tests the
orchestrator should run first after every implementation checkpoint"):

> Those three, in order, in under 90 seconds, eliminate ~70% of the
> possible failure surface.

**After every implementation checkpoint, run these three in order:**

### 1. T00 — Environment preflight (~5 s)
```
./venv/Scripts/python.exe scripts/audit.py
```
All lines must print `[ PASS ]`. Exit code must be 0.

### 2. T02 — CUDA smoke (~15 s)
```
./venv/Scripts/python.exe -c "import torch, whisper; print('cuda', torch.cuda.is_available(), torch.version.cuda); print('dev', torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)); m = whisper.load_model('small', device='cuda'); import numpy as np; _ = m.transcribe(np.zeros(16000, dtype=np.float32), language='en', fp16=True); print('inference OK')"
```
Must print `cuda True 12.4`, device name containing `4070 Ti SUPER`, `(8, 9)`, then `inference OK`. No exceptions.

### 3. T05 + T06 combined — Global hotkey end-to-end with clipboard (~45 s)
**[NEEDS gui_qt.py — skip before Phase 4]**

Open Notepad, focus it, then press Ctrl+Alt+Q; speak a short phrase; press
Ctrl+Alt+Q again to stop; focus Notepad and press Ctrl+V.

Pass criteria: start chime heard, transcription appears in MyTranscribe
window, text pastes into Notepad on Ctrl+V. Full details in §D T05 and T06.

---

## D. Individual test recipes

Each recipe is a direct expansion of the test case in
`docs/port-plan/03-risk-verification.md` §2. Commands are copy-paste ready.

---

### T00 — Environment preflight

**Risks covered:** R32, R33  
**Requires gui_qt.py:** No

**Command:**
```
./venv/Scripts/python.exe scripts/audit.py
```

**Expected output:**
```
[ PASS ] Python version is 3.11.x
[ PASS ] Running inside a venv
[ PASS ] ffmpeg on PATH
[ PASS ] torch.cuda.is_available() is True
[ PASS ] torch.cuda.get_device_name(0) returns a name
[ PASS ] whisper importable
[ PASS ] PyQt6.QtWidgets importable
[ PASS ] PyAudio importable and >=1 input device found
[ PASS ] pynput importable
[ PASS ] Temp dir writable
[ PASS ] Free disk space on temp dir >=500 MB
[ PASS ] Whisper cache dir exists or is creatable
```
Exit code: `0`

**Pass criteria:** Every line starts with `[ PASS ]`. Exit code 0.

**On failure:** The failing line identifies the broken check. Fix that
specific dependency before running any other test.

---

### T01 — Cold-start smoke (window paints, always-on-top, DPI)

**Risks covered:** R15, R20, R22  
**Requires gui_qt.py:** YES — skip before Phase 3

**Command (launch from project root):**
```
./venv/Scripts/python.exe src/gui_qt.py
```
To simulate a Start-menu launch (wrong cwd), open a separate terminal and run:
```
cd /c/Windows/System32 && ./c/Users/smich/Apps/MyTranscribe/venv/Scripts/python.exe C:/Users/smich/Apps/MyTranscribe/src/gui_qt.py
```

**Procedure:**
1. Run the command above.
2. Open Notepad, click inside it.
3. Observe the MyTranscribe window.

**Expected output:**
HUMAN: Window visible on top of Notepad within 3 s. Title bar reads
"Real-Time Transcription". Buttons readable at primary monitor DPI.
Window is semi-transparent (~90% opacity). Launching from System32 must
produce the same result (R15: relative path guard).

**Pass criteria:** Window appears, is always on top of Notepad, title correct,
not frozen, and works from a wrong-cwd launch.

**On failure:** Check `Qt.WindowStaysOnTopHint` is set before `show()`;
check `QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)` called before
`QApplication(sys.argv)`; check all file paths use `Path(__file__).parent`
not relative strings.

---

### T02 — CUDA smoke (model on GPU, first inference succeeds, driver OK)

**Risks covered:** R14, R17, R18  
**Requires gui_qt.py:** No

**Command:**
```
./venv/Scripts/python.exe -c "import torch, whisper; print('cuda', torch.cuda.is_available(), torch.version.cuda); print('dev', torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0)); m = whisper.load_model('small', device='cuda'); import numpy as np; _ = m.transcribe(np.zeros(16000, dtype=np.float32), language='en', fp16=True); print('inference OK')"
```

**Expected output:**
```
cuda True 12.4
dev NVIDIA GeForce RTX 4070 Ti SUPER (8, 9)
inference OK
```
Total runtime under 20 s.

**Pass criteria:** All three lines match (device name may differ slightly);
no exception; runtime < 20 s.

**On failure:** `cuda False` → update GeForce driver to >=550.x.
`no kernel image` → torch built for wrong CUDA version, reinstall with
`--index-url https://download.pytorch.org/whl/cu124`.

---

### T03 — Import smoke (no ModuleNotFoundError, no DLL load failures)

**Risks covered:** (general import health)  
**Requires gui_qt.py:** No

**Command:**
```
./venv/Scripts/python.exe -c "import PyQt6.QtWidgets, whisper, torch, pyaudio, pynput, numpy, wave, tempfile; print('all imports OK')"
```

**Expected output:**
```
all imports OK
```

**Pass criteria:** Exits 0, prints exactly `all imports OK`.

**On failure:** Note which module; `pip install <module>` or reinstall from
`requirements-windows.txt`.

---

### T04 — Mic selection smoke (correct device, shared mode, channels)

**Risks covered:** R01, R02, R03, R04, R35  
**Requires gui_qt.py:** YES (for step 3) — steps 1–2 are pre-Phase 3

**Command (device enumeration — run any time):**
```
./venv/Scripts/python.exe -c "import pyaudio; p=pyaudio.PyAudio(); [print(i, p.get_device_info_by_index(i)['name'], p.get_device_info_by_index(i)['maxInputChannels'], p.get_host_api_info_by_index(p.get_device_info_by_index(i)['hostApi'])['name']) for i in range(p.get_device_count()) if p.get_device_info_by_index(i)['maxInputChannels']>0]; p.terminate()"
```

**Procedure:**
1. Run the enumeration command. Note the index and name of the intended
   USB mic (look for it under the MME host API).
2. Ensure Discord/Teams/Voice Recorder is closed.
3. Launch the app, click Start, speak "one two three four five", click Stop.

**Expected output:**
HUMAN: Log line in terminal shows `Using input device #N: <name> via MME`
matching the device found in step 1. Transcription text contains
"one two three four five" (or very close).

**Pass criteria:** Correct mic used; transcription intelligible.

**On failure:** Wrong device chosen → set env var `MYTRANSCRIBE_MIC="<substring>"` and relaunch; update device picker logic to match by name.

---

### T05 — Global hotkey smoke (Ctrl+Alt+Q from another focused app)

**Risks covered:** R05, R06, R07  
**Requires gui_qt.py:** YES — skip before Phase 4

**Command:** Launch the app first:
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:**
1. With MyTranscribe running, open Notepad and click inside it.
2. With Notepad focused, hold Ctrl+Alt and tap Q.
3. Speak "hotkey test".
4. Hold Ctrl+Alt and tap Q again.

**Expected output:**
HUMAN: Start chime audible after step 2. End chime after step 4.
Transcription text "hotkey test" (or similar) appears in the MyTranscribe
window text area. MyTranscribe window is raised to foreground on start edge.

**Pass criteria:** Both chimes play; transcript appears; clipboard is populated
(verified in T06).

**On failure:** No chime → pynput blocked by AV; check Windows Defender
quarantine or add venv to Defender exclusions. Fires only when MyTranscribe
has focus → listener not started or connected to wrong thread.

---

### T06 — Clipboard smoke (setText then Ctrl+V into Notepad)

**Risks covered:** R08, R09, R10  
**Requires gui_qt.py:** YES — skip before Phase 4

**Precondition:** T05 just completed (clipboard holds transcript of "hotkey test").

**Command:**
Switch focus to Notepad and press Ctrl+V.

**Expected output:**
HUMAN: "hotkey test" (or the T05 transcript) pastes into Notepad on the
first Ctrl+V attempt. No Qt threading warning in the terminal.

**Pass criteria:** Text pastes on first try. No `QObject::setText: Cannot
send events to objects owned by a different thread` in terminal output.

**On failure:** Thread-safety warning in log → change clipboard signal
connection type to `Qt.QueuedConnection`; never call `QClipboard.setText`
from the PyAudio/Whisper worker thread.

---

### T07 — Long-record smoke (3-minute auto-stop fires cleanly)

**Risks covered:** R19, R36  
**Requires gui_qt.py:** YES — skip before Phase 3

**Command:** Launch the app:
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:**
1. Click "Long Record".
2. Speak for ~10 s, then stay silent.
3. Set a phone timer for 180 s and wait the full duration.

**Expected output:**
HUMAN: At ~180 s, end chime plays; transcription text appears in the text
area; Start and Long Record buttons re-enable; Stop button disables; audio
indicator hides. Terminal log shows `torch.cuda.memory_allocated` <= 3 GB.

**Pass criteria:** All button states correct; chime plays; no OOM error in log.

**On failure:** Buttons stuck → `recording_finished` signal not wired to
`update_button_states()` slot. OOM → add `torch.cuda.empty_cache()` after
each chunk.

---

### T08 — Audio indicator refresh rate

**Risks covered:** R22, R24  
**Requires gui_qt.py:** YES — skip before Phase 3

**Command:** Launch the app and start recording:
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:** Click Start, speak rhythmically (tap the mic or say "test" repeatedly).

**Expected output:**
HUMAN: The dark-green 50x4 px rounded rectangle in the top-right corner of
the text area blinks visibly in response to speech within ~100 ms. It is
visible (not zero pixels) at the current monitor DPI.

**Pass criteria:** Indicator responds to audio within one tick (~30–50 ms);
visible at primary monitor DPI.

**On failure:** Invisible → replace fixed pixel size with DPI-aware sizing
(`fontMetrics().height()` multiple). Sluggish → confirm timer runs on GUI
thread and is not blocked by paint events.

---

### T09 — Non-ASCII round-trip (accented chars, em-dash, curly quotes)

**Risks covered:** R26, R27  
**Requires gui_qt.py:** YES — skip before Phase 3

**Command:** Launch the app:
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:**
1. Start recording.
2. Speak clearly: `cafe resume — "it's fine"` (or any phrase with accented chars).
3. Stop.
4. Focus Notepad; press Ctrl+V.
5. In PowerShell, run:
   ```powershell
   Get-Clipboard | Out-File utf8.txt -Encoding utf8
   ```

**Expected output:**
HUMAN: Accented characters appear correctly in the MyTranscribe text area
and in Notepad paste. `utf8.txt` contains the correct characters. No
`UnicodeEncodeError` in terminal.

**Pass criteria:** No encoding exception; characters preserved end-to-end.

**On failure:** Add `sys.stdout.reconfigure(encoding='utf-8', errors='replace')`
at the app entry point; remove any bare `print()` calls that emit user text.

---

### T10 — Exit smoke (all three exit paths release resources)

**Risks covered:** R28, R29, R30, R31  
**Requires gui_qt.py:** YES — skip before Phase 3

**Procedure (run each sub-test separately):**

**10a — Ctrl+C from terminal:**
```
./venv/Scripts/python.exe src/gui_qt.py
```
Do one short recording. In the terminal, press Ctrl+C.

**10b — Close button (X):**
```
./venv/Scripts/python.exe src/gui_qt.py
```
Do one recording. Click the window's X button.

**10c — Hotkey stop then X:**
```
./venv/Scripts/python.exe src/gui_qt.py
```
Press Ctrl+Alt+Q (start), speak, press Ctrl+Alt+Q (stop), then click X.

**After each exit, within 5 s, run:**
```bash
tasklist | grep -i python
```
```
nvidia-smi
```
Then immediately relaunch the app.

**Expected output:**
HUMAN: No `python.exe` process remains after exit. `nvidia-smi` shows no
python.exe GPU allocation. Relaunch succeeds without "Device unavailable".

**Pass criteria:** All three paths: zero zombie process, no lingering GPU
memory, mic available on next launch.

**On failure:** (a) Add `signal.signal(signal.SIGINT, signal.SIG_DFL)` after
`QApplication(sys.argv)`. (b) Add `PyAudio.terminate()` in `closeEvent`.
(c) Add `listener.stop(); listener.join(timeout=2.0)` in `closeEvent`;
fall back to `os._exit(0)` if join times out.

---

### T11 — Temp WAV lock / AV race

**Risks covered:** R11, R12, R13  
**Requires gui_qt.py:** YES — skip before Phase 3

**Precondition:** Windows Defender real-time protection ON (default state).

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:** Do 10 short recordings (3 s each) back-to-back via Ctrl+Alt+Q.
Watch the terminal log for errors.

**Expected output:** No `PermissionError` lines. No `[Transcription Error: ...]`
lines. All 10 recordings produce text in the text area.

**Pass criteria:** Zero error lines across all 10 recordings.

**On failure:** The `os.remove` guard in `transcriber_v12.py` (Phase 1 patch)
should handle most cases. If `model.transcribe` itself raises PermissionError,
add a retry-on-PermissionError with 100 ms sleep around the call. Consider
adding `%TEMP%\*.wav` to Windows Defender exclusions.

---

### T12 — Model load non-blocking (UI responsive during cold start)

**Risks covered:** R17  
**Requires gui_qt.py:** YES — skip before Phase 3

**Precondition:** Cold start — last launch was >=5 min ago.

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```
Immediately after running the command (within 1 s), try to drag the window.

**Expected output:**
HUMAN: Window responds to drag within 200 ms even while model is loading.
Buttons may show a "Loading..." state, but the window is not frozen.

**Pass criteria:** Window draggable within 200 ms of appearing.

**On failure:** Move `whisper.load_model()` into a `QThread`; show a
"Loading model..." label until the thread signals completion; gate the hotkey
listener until after model load.

---

### T13 — DPI and multi-monitor rendering

**Risks covered:** R21, R22  
**Requires gui_qt.py:** YES — skip before Phase 3

**Note:** If only one monitor is connected, perform the single-monitor
portion only.

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:**
1. Launch on primary monitor.
2. If a second monitor is connected, drag the window to it.
3. Observe opacity and widget sizes on each monitor.

**Expected output:**
HUMAN: Window opacity approximately 90% on all monitors. Buttons legible.
Audio indicator visible (not zero pixels). No rendering artifacts or
full-opacity flash on monitor switch.

**Pass criteria:** All widgets legible and correctly sized on all connected
monitors.

**On failure:** Ensure `QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)`
is called BEFORE `QApplication(sys.argv)`.

---

### T14 — Button click flow (basic end-to-end via mouse)

**Risks covered:** R23, R25  
**Requires gui_qt.py:** YES — skip before Phase 3

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:** Click Start. Speak a short phrase. Click Stop.

**Expected output:**
HUMAN: Start chime plays on Start click; Stop chime plays on Stop click;
transcription text appears in the text area; text is on the clipboard
(verify via Ctrl+V into Notepad). Start and Long Record re-enable; Stop
disables.

**Pass criteria:** Same behavior as hotkey path (T05). No threading warning
in log.

**On failure:** Button signal wired to wrong slot, or a thread-boundary
widget call. Check slot connections; confirm `QClipboard.setText` is called
from the GUI thread only.

---

### T15 — Normal-mode 5-minute duration (stress test)

**Risks covered:** R19, R23  
**Requires gui_qt.py:** YES — skip before Phase 3

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:** Click Start. Speak intermittently for 5 minutes. Click Stop.

**Expected output:**
HUMAN: Chunks transcribed and appended live approximately every 300 s.
Final concatenation appears on Stop. Log shows `torch.cuda.memory_allocated`
<= 4 GB peak. No UI freeze lasting more than 1 s.

**Pass criteria:** Full 5-minute session completes without error, OOM, or UI
freeze >1 s.

**On failure:** T07 mitigations (empty_cache); check `DEFAULT_CHUNK_DURATION`
is respected.

---

### T16 — Repeated hotkey spam (debounce / race safety)

**Risks covered:** R08, R29  
**Requires gui_qt.py:** YES — skip before Phase 4

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:** Press Ctrl+Alt+Q, immediately Ctrl+Alt+Q again. Pause 1 s.
Repeat this cycle 10 times.

**Expected output:** Each press toggles state. No crash, no stuck state after
10 cycles. Clipboard ends with the last non-empty transcription (or empty if
silence).

**Pass criteria:** App still responsive after 10 rapid toggles. No exception
in log.

**On failure:** Add debounce in `on_global_press`; ensure `self.q_pressed`
resets on every fire.

---

### T17 — WASAPI exclusive-mode regression

**Risks covered:** R02  
**Requires gui_qt.py:** YES — skip before Phase 3

**Precondition:** In Windows Sound Settings, find the chosen mic's Properties >
Advanced > check "Allow applications to take exclusive control".

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:**
1. Start a recording in MyTranscribe.
2. Open Windows Voice Recorder and attempt to record.

**Expected output:**
HUMAN: Both apps can record simultaneously (MyTranscribe uses shared mode).

**Pass criteria:** MyTranscribe does not block Voice Recorder; no
`-9985 Device unavailable` error in MyTranscribe log.

**On failure:** Explicit host API selection missing in `start_recording`;
force MME or WASAPI-shared by selecting the appropriate `input_device_index`.

---

### T18 — Device index drift (USB re-enumeration)

**Risks covered:** R03  
**Requires gui_qt.py:** YES — skip before Phase 3

**Precondition:** MyTranscribe just worked with the USB mic (T04 passed).

**Procedure:**
1. Unplug the USB mic.
2. Plug in any other USB device (storage, keyboard).
3. Re-plug the USB mic.
4. Relaunch MyTranscribe.
5. Do a recording.

**Expected output:**
HUMAN: MyTranscribe still selects the correct mic. Transcription is
intelligible.

**Pass criteria:** Correct device used after re-enumeration.

**On failure:** Device lookup is by index; change to name-substring match in
the device picker logic.

---

### T19 — Stereo-mic downmix

**Risks covered:** R04  
**Requires gui_qt.py:** YES — skip before Phase 3

**Precondition:** Check `maxInputChannels` for the chosen device via T04
step 1. If it is 1, this test is N/A — mark as SKIP.

**Command (channel check):**
```
./venv/Scripts/python.exe -c "import pyaudio; p=pyaudio.PyAudio(); info=p.get_default_input_device_info(); print('channels:', info['maxInputChannels']); p.terminate()"
```

**Procedure (if stereo):** Record "left right test" speaking into the mic.

**Expected output:** Transcription contains all three words.

**Pass criteria:** All words transcribed (no silent-channel truncation).

**On failure:** Open PyAudio stream with `channels=<device max>`; downmix
`(L+R)/2` to mono ndarray before WAV write.

---

### T20 — Hotkey with elevated foreground app (known limitation)

**Risks covered:** R05, R07  
**Requires gui_qt.py:** YES — skip before Phase 4

**Precondition:** MyTranscribe running unelevated.

**Procedure:** Open Task Manager (which runs elevated by default on Windows
11). With Task Manager focused, press Ctrl+Alt+Q.

**Expected output:** Hotkey does NOT fire. This is working as designed.
The limitation (unelevated pynput cannot observe input directed at elevated
windows) is documented in R05.

**Pass criteria (of the known-limitation kind):** Hotkey does not fire.
No crash.

**On failure (fires unexpectedly):** Surprising — no action needed.

---

### T21 — Clipboard from worker thread (static code review)

**Risks covered:** R08, R23  
**Requires gui_qt.py:** YES — code review after Phase 4

**Command:**
```bash
grep -n "clipboard\|setText" src/gui_qt.py
```

**Procedure:** Inspect every line returned. Confirm each is either:
(a) inside a slot function that is connected via `Qt.AutoConnection` or
    `Qt.QueuedConnection`, or
(b) inside a `QTimer.singleShot` callback on the GUI thread.

Zero occurrences in `record_loop`, `process_audio_chunk`, or any method
called from a worker `QThread` or `threading.Thread`.

**Pass criteria:** No direct `QClipboard.setText` calls reachable from a
non-GUI thread.

**On failure:** Refactor — route clipboard writes through a
`pyqtSignal(str)` on a `QObject` owned by the main thread.

---

### T22 — Clipboard paste into Electron app

**Risks covered:** R09  
**Requires gui_qt.py:** YES — skip before Phase 4

**Precondition:** Discord or VS Code running with a focused text input field.

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:** Record "paste test", let it finish, focus the Discord/VS Code
input field, press Ctrl+V.

**Expected output:**
HUMAN: Text pastes on the first Ctrl+V attempt.

**Pass criteria:** Paste succeeds on first try with no delay.

**On failure:** Add `QTimer.singleShot(50, lambda: clipboard.setText(final_text))`
before emitting the "done" signal in the hotkey stop path.

---

### T23 — Defender scanning latency (large WAV)

**Risks covered:** R11, R25  
**Requires gui_qt.py:** YES — skip before Phase 3

**Precondition:** Windows Defender real-time protection ON.

**Command:**
```
./venv/Scripts/python.exe src/gui_qt.py
```

**Procedure:** Click "Long Record". Speak for 5+ minutes (to produce a
large WAV file). Click Stop. Watch the terminal log.

**Expected output:** No `[Transcription Error: ...]` lines. Transcription
completes successfully.

**Pass criteria:** Zero transcription errors on a large WAV with Defender active.

**On failure:** Add retry loop around `model.transcribe(path)` for
`PermissionError`; add `%TEMP%\*.wav` to Defender exclusions if retries fail.

---

### T24 — GPU memory regression (5 long sessions)

**Risks covered:** R19  
**Requires gui_qt.py:** YES — skip before Phase 3

**Procedure:**
1. Note baseline: run `nvidia-smi` and record the python.exe GPU memory value.
2. Do 5 long-record sessions (3 min each) via "Long Record" button.
3. Re-run `nvidia-smi`.

**Expected output:**
Python.exe GPU memory usage does not grow by more than 500 MB from
baseline to end of session 5.

**Pass criteria:** Delta < 500 MB across 5 sessions.

**On failure:** Add `torch.cuda.empty_cache()` after each `stop_recording()`
and after each `process_audio_chunk()` call.

---

### T25 — Always-on-top under UAC prompt

**Risks covered:** R20  
**Requires gui_qt.py:** YES — skip before Phase 3

**Precondition:** MyTranscribe running.

**Procedure:** Trigger a UAC prompt (e.g., right-click cmd.exe → Run as
administrator). Observe whether MyTranscribe stays visible.

**Expected output:**
HUMAN: UAC prompt takes foreground (secure desktop). MyTranscribe window
is temporarily hidden or obscured. On dismissal of the UAC prompt,
MyTranscribe returns on top.

**Pass criteria (known limitation):** UAC hides MyTranscribe during secure
desktop — this is correct behavior. MyTranscribe must resume on top after
dismissal. No crash.

**On failure:** Document. No fix available without kernel-level hooks.

---

## E. Regression triage flowchart

```
Start: which test failed?
│
├── T00 fails
│   └── Check the specific failing audit line:
│       • "torch.cuda" → driver update or wrong torch build
│       • "ffmpeg" → ffmpeg not on PATH or venv PATH issue
│       • "PyAudio >=1 device" → mic unplugged or driver missing
│       • "venv active" → forgot to activate venv
│       • "temp dir" → %TEMP% on OneDrive or disk full
│
├── T03 fails (import error) but T00 passes
│   └── Missing package; pip install the named module;
│       if DLL load error → reinstall with matching CUDA index-url
│
├── T02 fails but T00 passes
│   └── torch importable but CUDA broken → GeForce driver < 550.x;
│       or torch built for different CUDA version (check torch.version.cuda)
│
├── T01 fails (window does not appear or wrong DPI)
│   └── Qt.WindowStaysOnTopHint missing or set after show();
│       AA_EnableHighDpiScaling not called before QApplication()
│
├── T05 fails (hotkey does not fire) but T14 passes (buttons work)
│   └── pynput listener not started, or started after GUI event loop;
│       check AV quarantine; confirm listener is on background thread,
│       not blocking the GUI thread
│
├── T06 fails (paste empty or wrong content) but T05 passes
│   └── QClipboard.setText called from worker thread;
│       check for Qt threading warning in log;
│       fix by routing through pyqtSignal + QueuedConnection
│
├── T11 fails (PermissionError on os.remove or model.transcribe)
│   └── Phase 1 os.remove guard may be missing;
│       verify transcriber_v12.py patch applied;
│       add %TEMP%\*.wav to Defender exclusions if retries still fail
│
└── T07 fails (buttons stuck after 180 s auto-stop) but T14 passes
    └── recording_finished signal not connected to update_button_states();
        check that record_loop's natural exit emits the signal
```

---

## F. Baseline known-good audit output

Run date: 2026-04-18  
Machine: Windows 11, RTX 4070 Ti Super, Python 3.11.9, venv at
`C:\Users\smich\Apps\MyTranscribe\venv`

Command run:
```
./venv/Scripts/python.exe scripts/audit.py
```

Verbatim output:
```
[ PASS ] Python version is 3.11.x  (3.11.9)
[ PASS ] Running inside a venv  (C:\Users\smich\Apps\MyTranscribe\venv)
[ PASS ] ffmpeg on PATH  (C:\ProgramData\chocolatey\bin\ffmpeg.EXE)
[ PASS ] torch.cuda.is_available() is True  (torch 2.6.0+cu124 / cuda 12.4)
[ PASS ] torch.cuda.get_device_name(0) returns a name  (NVIDIA GeForce RTX 4070 Ti SUPER)
[ PASS ] whisper importable
[ PASS ] PyQt6.QtWidgets importable
[ PASS ] PyAudio importable and >=1 input device found  (13 input device(s) found)
[ PASS ] pynput importable
[ PASS ] Temp dir writable  (C:\Users\smich\AppData\Local\Temp)
[ PASS ] Free disk space on temp dir >=500 MB  (98049 MB free on C:\Users\smich\AppData\Local\Temp)
[ PASS ] Whisper cache dir exists or is creatable  (C:\Users\smich\.cache\whisper)
```

Exit code: `0`

All 12 checks passed. PyQt6 was already installed at the time of capture.
If PyQt6 has not yet been installed (pre-Phase 2), that line will show
`[ FAIL ] PyQt6.QtWidgets importable — not found — pip install PyQt6`
and the exit code will be `1`; that is expected and acceptable before Phase 2.
