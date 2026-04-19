# MyTranscribe Windows Port — Human Verification Hand-off

**Phase 5 hand-off document.**
Programmatic tests complete. This document covers the tests a human must run
because they require a microphone, real keyboard capture from another process,
or visual/audio observation.

---

## §A — Purpose

The programmatic verification suite (Phase 5) covered everything that can be
checked without real audio hardware or a live desktop session: environment
preflight (T00), import smoke (T03), CUDA + model inference (T02), cold-launch
subprocess (T01 variant), mic enumeration (T04 step 1), stereo-mic channel
check (T19 step 1), clipboard thread-safety code review (T21), and the full
Phase 4 state-machine smoke test (synthetic signal emit, LongRecording no-op,
closeEvent teardown). All passed.

The tests in this document require a human to:
- Listen for chime audio
- Speak into the microphone
- Interact with real applications (Notepad, a terminal)
- Observe window behavior (opacity, always-on-top, focus)

Total estimated time: **10-15 minutes** for a single pass.

---

## §B — Setup checklist (do once before running any test)

- [ ] Microphone plugged in and **not muted** in Windows Sound settings
      (Settings > System > Sound > your mic device > ensure volume > 0 and not muted)
- [ ] Notepad ready — open it now: `Win+R`, type `notepad`, press Enter
- [ ] Close any UAC-elevated or fullscreen apps (Task Manager in elevated mode,
      games in fullscreen) — pynput cannot capture hotkeys directed at elevated windows
- [ ] Close Discord, Teams, or any app that may hold the mic exclusively
- [ ] Open a terminal (Windows Terminal or Git Bash) in the project directory
      with the venv activated:
      ```
      cd C:/Users/smich/Apps/MyTranscribe
      source venv/Scripts/activate
      ```
- [ ] Keep this document visible alongside the terminal (second monitor, split
      screen, or printed copy)

---

## §C — Test sequence

Run the tests in order. **Stop at the first failure** and record the result
before continuing, so the failure context is preserved.

---

### HT-01 — Cold launch visual check

**Corresponds to:** T01  
**Precondition:** No other instance of `gui_qt.py` running.

**Steps:**
1. In the terminal, run:
   ```
   ./venv/Scripts/python.exe src/gui_qt.py
   ```
2. Click anywhere inside the Notepad window to give it focus.
3. Observe the MyTranscribe window.

**Expected:**
- Window appears within 3 seconds.
- Title bar reads "Real-Time Transcription".
- Window is **semi-transparent** (~90% opacity — slightly see-through).
- Window is **always on top** of Notepad (not hidden behind it).
- Three buttons visible: green "Start", red "Stop", blue "Long Record".
- "Stop" is greyed-out (disabled).
- No error messages in the terminal.

**Pass / Fail:** [ ]

**If fail:**
- Window does not appear: check terminal for `ImportError` or `ModuleNotFoundError`.
- Not on top: `WindowStaysOnTopHint` may have been stripped; check `gui_qt.py` around line 273.
- Wrong opacity: check `setWindowOpacity(0.9)` call around line 278.

---

### HT-02 — Mouse Start → speak → Stop → transcription

**Corresponds to:** T14  
**Precondition:** App running from HT-01. Window visible.

**Steps:**
1. Click the green **Start** button.
2. Listen for the start chime (short audio tone).
3. Speak clearly into the microphone: **"The quick brown fox jumps over the lazy dog."**
4. Wait 2 seconds after you finish speaking.
5. Click the red **Stop** button.
6. Listen for the stop chime.
7. Observe the text area in the MyTranscribe window.

**Expected:**
- Start chime plays immediately when Start is clicked.
- Stop button becomes enabled; Start and Long Record become disabled.
- After Stop: Stop button disables; Start and Long Record re-enable.
- Stop chime plays.
- Transcription text appears in the text area (close approximation of spoken phrase; Whisper may vary slightly).
- No threading warnings in the terminal (no lines containing `QObject::setText`).

**Pass / Fail:** [ ]

**If fail:**
- No chime: check `sound_utils.py` / `ChimePlayer`; ensure speakers not muted.
- Buttons do not change state: check `_set_state()` wiring.
- No transcription: check terminal for `[Transcription Error]`; may be mic not selected.
- Threading warning in log: clipboard write is happening off-thread; see T21 fix.

---

### HT-03 — Clipboard auto-copy (Ctrl+V into Notepad)

**Corresponds to:** T06  
**Precondition:** HT-02 just completed; transcription text is in the text area.

**Steps:**
1. Click inside the Notepad window to focus it.
2. Press **Ctrl+V**.

**Expected:**
- The transcription text from HT-02 pastes into Notepad on the first Ctrl+V.
- No second paste needed; no stale content from before HT-02.

**Pass / Fail:** [ ]

**If fail:**
- Nothing pasted: clipboard write may be failing silently; add print in `_finalize_and_copy`.
- Wrong text pasted: clipboard was overwritten by another app between HT-02 and this step.

---

### HT-04 — Spacebar starts normal recording (window focused, Idle state)

**Corresponds to:** T14 spacebar variant  
**Precondition:** App in Idle state (from HT-02/HT-03 end). MyTranscribe window focused
(click its title bar to focus it).

**Steps:**
1. Click the MyTranscribe **title bar** to ensure the window has keyboard focus.
2. Press the **Spacebar** once.
3. Listen for the start chime.
4. Speak: **"Spacebar start test."**
5. Press the **Spacebar** again.
6. Listen for the stop chime.
7. Observe the text area.

**Expected:**
- First Space: start chime plays; Stop button enables; Start/Long Record disable.
- Second Space: stop chime plays; Stop disables; Start/Long Record re-enable.
- Transcription text appears (approximately "Spacebar start test.").
- Clipboard is updated (verify by switching to Notepad and pressing Ctrl+V).

**Pass / Fail:** [ ]

**If fail:**
- Space does nothing: `keyPressEvent` may not be receiving events; check `setFocusPolicy`
  on buttons is `NoFocus` and window focus is set.
- Space activates a button instead of the handler: a button has focus; `NoFocus` may be missing.

---

### HT-05 — LongRecording Space/Ctrl+Alt+Q no-op contract

**Corresponds to:** T07 partial + T16 partial  
**Precondition:** App in Idle state.

**Steps:**
1. Click the blue **Long Record** button.
2. Listen for the start chime.
3. Confirm text area shows "Recording in long mode..."
4. With the MyTranscribe window focused, press **Spacebar** once.
5. Observe: nothing should change (no chime, no state transition).
6. Press **Ctrl+Alt+Q** once.
7. Observe: nothing should change (no chime, no state transition).
8. Click the red **Stop** button.
9. Listen for the stop chime.
10. Confirm Stop button disables; Start and Long Record re-enable.

**Expected:**
- Steps 4 and 6: absolutely no response — no chime, no state change, no error in terminal.
- Step 8-10: normal stop, state returns to Idle.

**Pass / Fail:** [ ]

**If fail:**
- Space or Ctrl+Alt+Q stops Long Record: the no-op guards in `keyPressEvent` and `on_hotkey` are missing or incorrect; check `gui_qt.py` around lines 527-534 and 548-558.

---

### HT-06 — Global hotkey from another focused app (Notepad)

**Corresponds to:** T05  
**Precondition:** App in Idle state. Notepad open and focused.

**Steps:**
1. Click inside the **Notepad** window so it has focus.
2. Hold **Ctrl+Alt** and tap **Q** (press and release Q while holding Ctrl and Alt).
3. Listen for the start chime.
4. Observe the MyTranscribe window.
5. Speak clearly: **"Global hotkey test one two three."**
6. Hold **Ctrl+Alt** and tap **Q** again to stop.
7. Listen for the stop chime.
8. Switch focus back to Notepad; press **Ctrl+V**.

**Expected:**
- Step 2: start chime plays; MyTranscribe window raises to foreground.
- Step 4: Stop button enabled; Start/Long Record disabled.
- Step 6: stop chime plays; state returns to Idle.
- Step 8: transcription text pastes into Notepad.

**Pass / Fail:** [ ]

**If fail:**
- No chime at step 2: pynput listener may be blocked by AV or not running;
  check terminal for "pynput keyboard listener started". Try adding venv to
  Windows Defender exclusions.
- Hotkey fires only when MyTranscribe has focus: listener not started or
  connected to wrong thread.
- Text does not paste: clipboard write failing; see T06 / T21 mitigations.

---

### HT-07 — Audio indicator pulses on speech (Long Record mode)

**Corresponds to:** T08  
**Precondition:** App in Idle state.

**Steps:**
1. Click **Long Record**.
2. Listen for the start chime.
3. Speak several syllables rhythmically: **"test test test test test."**
4. Watch the top-right corner of the text area for a small dark-green rectangle.
5. Click **Stop**.

**Expected:**
- A dark-green rounded rectangle (~50x4 px) appears in the top-right corner of
  the text area while speech is detected.
- It disappears (or blinks) during silence.
- It is visible at the current monitor DPI (not zero pixels).

**Pass / Fail:** [ ]

**If fail (non-blocking):**
- Indicator not visible: may be DPI sizing issue; note it but do not block the port.
- Indicator jumps on resize: known risk per impl spec §15 — note it, not a blocker.

---

### HT-08 — Clean exit via window close button

**Corresponds to:** T10b  
**Precondition:** App in Idle state.

**Steps:**
1. Do one short recording (Spacebar start, speak, Spacebar stop).
2. Click the window's **X (close) button**.
3. Within 5 seconds, in the terminal, run:
   ```
   tasklist | grep -i python
   ```
4. Immediately relaunch: `./venv/Scripts/python.exe src/gui_qt.py`

**Expected:**
- After X click, the terminal returns to the shell prompt within 3 seconds.
- `tasklist | grep -i python` shows no `python.exe` lines (or none related to MyTranscribe).
- Relaunch succeeds without "Device unavailable" or "port already in use" errors.

**Pass / Fail:** [ ]

**If fail:**
- Process does not exit: `closeEvent` may not call `QApplication.quit()`; see gui_qt.py line 597.
- Relaunch fails with "Device unavailable": PyAudio not terminated on close; check `_chime.cleanup()` and `_transcriber.stop_recording()` in `closeEvent`.

---

### HT-09 — Clean exit via Ctrl+C in terminal

**Corresponds to:** T10a  
**Precondition:** App not running; fresh launch.

**Steps:**
1. Run: `./venv/Scripts/python.exe src/gui_qt.py`
2. Do one short recording.
3. In the terminal, press **Ctrl+C**.
4. Run: `tasklist | grep -i python`
5. Immediately relaunch: `./venv/Scripts/python.exe src/gui_qt.py`

**Expected:**
- Ctrl+C kills the process within 2-3 seconds.
- No `python.exe` process remains.
- Relaunch succeeds cleanly.

**Pass / Fail:** [ ]

**If fail:**
- Ctrl+C ignored: `signal.signal(signal.SIGINT, signal.SIG_DFL)` missing; check gui_qt.py line 606.
- Process lingers: pynput listener not stopped; `os._exit(0)` fallback may be needed.

---

### HT-10 — Re-launch after clean exit (no stuck resources)

**Corresponds to:** T18 partial  
**Precondition:** HT-08 or HT-09 just completed; app is not running.

**Steps:**
1. Launch: `./venv/Scripts/python.exe src/gui_qt.py`
2. Do one short recording (Spacebar start, speak one sentence, Spacebar stop).
3. Confirm transcription appears and clipboard is updated (Ctrl+V into Notepad).

**Expected:**
- No "Device unavailable", "-9985", or "port in use" errors in the terminal.
- Recording and transcription work normally.

**Pass / Fail:** [ ]

**If fail:**
- "Device unavailable": PyAudio resource held from prior session; check `closeEvent`
  cleanup order; ensure `pa.terminate()` is called.

---

## §D — Known non-blockers

These issues may surface during the human test pass. They are expected behaviors
or documented limitations — they should be noted but do **not** block acceptance
of the Windows port:

1. **First-inference CUDA warmup (5-10 seconds):** On first click of Start, the
   app may appear frozen for up to 10 seconds while Whisper loads the model onto
   the GPU. This is the lazy-load design from Phase 3. The window remains
   draggable. Subsequent recordings start instantly.

2. **Audio indicator positioning on resize:** If you resize the MyTranscribe
   window during recording, the dark-green indicator may jump or briefly disappear.
   This is a known risk from impl spec §15 (QTextEdit viewport resize relay).
   It resolves itself on the next poll tick (30 ms). Flag it in notes but do not
   block.

3. **Whisper hallucination filtering may drop very short utterances:** If you say
   only "hello" or a single short word, Whisper may return an empty or filtered
   result. Always test with a full sentence ("The quick brown fox..."). This is
   Whisper behavior, not a port defect.

4. **Ctrl+Alt+Q does not fire when Task Manager (or any elevated process) is
   focused (T20):** This is working-as-designed. pynput running unelevated cannot
   intercept input directed at elevated windows. Not a bug.

5. **First Long Record session after cold start:** The same 5-10 s CUDA warmup
   applies. The text area shows "Recording in long mode..." during this wait.

---

## §E — Rollback

If the port is unusable (app crashes on launch, no audio, hotkey completely
non-functional), revert to the Linux GTK3 version as follows:

Switch to the `main` branch (which still has `src/gui-v0.8.py` and the GTK3
setup), delete the Windows venv, and re-clone or re-checkout as needed:

```bash
git checkout main
deactivate
rm -rf venv
# On Linux/WSL, recreate the original venv with requirements.txt
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The `claude/windows-port-pyqt6` branch and all plan documents under
`docs/port-plan/` are preserved and can be rebased onto a future fix without
losing work.

---

*Document generated: 2026-04-18 — Phase 5 programmatic suite: 8/8 PASS.*
*Human test pass pending.*
