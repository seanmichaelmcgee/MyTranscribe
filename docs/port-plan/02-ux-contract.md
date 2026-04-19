# UX Fidelity Contract — PyQt6 Windows Port

Scope: behavior-preserving port of `src/gui-v0.8.py` (GTK3) to PyQt6 on Windows.
This document is the **behavioral** contract; Phase 2 implementers should be
able to build the GUI from this document alone without re-reading the GTK3
source. All references to widget state are driven by the backend surfaces
`RealTimeTranscriber` (`src/transcriber_v12.py`) and `ChimePlayer`
(`src/sound_utils.py`).

Conformance levels:

- **MUST** — implementation must match; deviation is a defect.
- **SHOULD** — preferred; deviation is acceptable if justified.
- **MAY drop** — Linux/GTK-specific; skip or replace on Windows.

---

## 1. Window behavior

1.1 **MUST** — Default size: 650 x 200 logical pixels.
1.2 **MUST** — Position on first show: centered on the primary monitor.
1.3 **MUST** — Title (window and any titlebar text): `Real-Time Transcription`.
1.4 **MUST** — Always-on-top: the window stays above other non-topmost windows for its entire lifetime. This is not toggleable from the UI.
1.5 **MUST** — Window opacity: `0.9` (whole window, including title bar and content) at all times.
1.6 **MUST** — Close button: visible and functional. Closing the window terminates the application (see §6.4).
1.7 **MUST** — Resizable: the window must be user-resizable. Vertical and horizontal growth must expand the transcription text area (§2.2); the button row stays fixed height at the bottom.
1.8 **SHOULD** — Minimum size: 400 x 150 logical pixels (to keep the 3-button row legible). Source does not enforce a minimum; this is a Windows refinement.
1.9 **MUST** — Startup state: window is shown immediately (not minimized, not hidden, not maximized). No splash screen.
1.10 **MUST** — Global-hotkey focus behavior: when the user presses `Ctrl+Alt+Q` from any app, the MyTranscribe window must be raised to the foreground, activated, and given focus — even if it was minimized or behind other windows. This happens only on the *start* edge of the hotkey (the one that transitions Idle → Normal Recording), not on the stop edge. The behavior mirrors GTK's `window.present()`.
1.11 **SHOULD** — Use **native Windows chrome** (standard title bar with the system menu, minimize/maximize/close). Do **not** replicate GTK's client-side `HeaderBar`. Rationale: the HeaderBar on Linux existed because GNOME removed the system title bar; on Windows, the native title bar already provides close/minimize/maximize, so a custom chrome would feel foreign. The title text must still read `Real-Time Transcription`.
1.12 **MAY drop** — GTK's `set_titlebar(HeaderBar)` customization. Native Windows chrome replaces it.

---

## 2. Widget catalog

All colors are hex RGB, matching the current GTK CSS exactly (`apply_css()` in
`gui-v0.8.py` lines 24-52).

### 2.1 Transcription text area

- **Name**: `transcription_view`
- **Purpose**: displays live / final transcribed text; read-only.
- **MUST** — Editable: **no**. User cannot type into it.
- **MUST** — Cursor visible: **no** (no blinking caret).
- **MUST** — Word wrap: on, at word boundaries (no mid-word breaks).
- **MUST** — Vertical scrollbar: shown automatically when content exceeds height.
- **MUST** — Horizontal scrollbar: shown automatically if somehow needed (wrap-on means this is rare).
- **MUST** — Expands to fill all vertical and horizontal space above the button row.
- **SHOULD** — Default system UI font (proportional). Source does **not** set a monospace font, so the port should also use the default (not monospace).
- **MUST** — Updated only from the GUI thread (see §6).
- **MUST** — Content replacement semantics: each update replaces the entire buffer with the latest joined transcription list — the view does not append line-by-line. (See `update_transcription_callback`.)
- **MUST** — Content cleared to empty string at the start of every new recording.

### 2.2 Start button

- **Name**: `start_button`
- **Label**: `Start`
- **Background color**: `#00FF00` (pure green).
- **Foreground color**: `black`.
- **Font weight**: bold.
- **Position**: left side of button row.
- **Horizontal sizing**: expands to share half of the left portion of the button row (it splits the left portion evenly with `stop_button`).
- **Interactive states**:
  - **MUST** — Enabled when app state is `Idle` only. Disabled (greyed/inert) in every recording/transcribing state.
  - Hover/pressed: standard OS visual feedback over the green fill is acceptable; the underlying fill must remain the specified green.
- **Driver**: `self.transcribing == False` -> enabled; else disabled.

### 2.3 Stop button

- **Name**: `stop_button`
- **Label**: `Stop`
- **Background color**: `#FF0000` (pure red).
- **Foreground color**: `black`.
- **Font weight**: bold.
- **Position**: left side of button row, immediately to the right of `Start`.
- **Horizontal sizing**: shares the left portion with `Start`.
- **Interactive states**:
  - **MUST** — Enabled only while a recording (normal or long) is in progress. Disabled in `Idle`.
- **Driver**: `self.transcribing == True` -> enabled; else disabled.

### 2.4 Long Record button

- **Name**: `long_record_button`
- **Label**: `Long Record`
- **Background color**: `#0000FF` (pure blue).
- **Foreground color**: `black`.
- **Font weight**: bold.
- **Position**: right side of button row (GTK `pack_end`). This must be **visually anchored to the right edge** of the button row, with the Start/Stop pair on the left.
- **Horizontal sizing**: expands similarly to Start/Stop.
- **Interactive states**:
  - **MUST** — Enabled when app state is `Idle` only. Disabled while any recording is in progress.
- **Driver**: `self.transcribing == False` -> enabled; else disabled.

### 2.5 Audio activity indicator

- **Name**: `audio_indicator`
- **Purpose**: visual confirmation that the microphone is picking up voice-level audio (RMS > 300 on 16-bit int samples at 16 kHz).
- **MUST** — Shape: solid filled rectangle, `50 x 4` logical pixels.
- **MUST** — Color: `#00AA00` (dark green).
- **MUST** — Corner radius: 2 logical pixels (rounded rectangle). Matches the CSS `border-radius: 2px`.
- **MUST** — Position: overlaid on the **top-right corner** of the transcription text area, with 5 px margin from the top and 5 px margin from the right edge of the text area. It does not displace text — text flows underneath it.
- **MUST** — Visibility rules:
  - Hidden on app start.
  - While recording (either mode): shown whenever `transcriber.audio_detected == True`, hidden when it becomes `False`. This polls the backend flag at the GUI update tick (see §6.2).
  - Hidden immediately when recording stops (on entry to `Idle`).
- **MUST** — Non-interactive. No click, no hover behavior, no tooltip.
- **SHOULD NOT** animate (no pulsing, no fade). The source shows/hides discretely; the tick rate (~33 Hz) and the 300 ms backend latch in `audio_detection_counter` together produce the perceived "pulse" — no extra animation is needed.

### 2.6 Button row container

- **MUST** — Horizontal layout, spacing 10 logical pixels between buttons.
- **MUST** — 10 logical pixel margin around the entire window's content area (matches `set_border_width(10)`).
- **MUST** — Fixed vertical height (do not grow when window is resized taller).
- **MUST** — Button order left-to-right: `Start`, `Stop`, ..., `Long Record` (with the gap between Stop and Long Record filling available space).

### 2.7 Widgets NOT present (do not add)

- No menu bar.
- No toolbar.
- No status bar.
- No progress bar.
- No settings dialog, preferences, or model picker.
- No tray icon.
- No notifications (toasts, system notifications, etc.).
- No "copied to clipboard" confirmation UI — the only feedback on copy is a `print` to stdout (keep as `logging` on Windows).

---

## 3. State machine

### 3.1 States

| State | Description |
| --- | --- |
| `Idle` | No recording active. Transcriber idle. Audio indicator hidden. |
| `NormalRecording` | `recording_mode = "normal"`, incremental chunked transcription running, GUI ticking at ~30 ms polling `transcriber.transcriptions`. |
| `LongRecording` | `recording_mode = "long"`, audio being accumulated; text area shows static placeholder `"Recording in long mode..."`. Auto-ends at 180 s backend-side. |
| `Stopping` (transient) | Between user stop trigger and the moment `stop_recording()` returns. Treat as same widget state as `Idle`; it is brief. |

Note: there is **no explicit `Transcribing` or `Error` state** in the current GUI. Whisper inference runs inline in the recorder's background thread; errors are inserted into the transcription list as text (`[Transcription Error: ...]`). The port must mirror this: no error modal, no separate state.

### 3.2 Allowed transitions

| From | Event | To | Notes |
| --- | --- | --- | --- |
| `Idle` | `Start` button clicked | `NormalRecording` | Plays start chime. |
| `Idle` | Spacebar pressed while window focused | `NormalRecording` | Plays start chime. |
| `Idle` | Global hotkey `Ctrl+Alt+Q` | `NormalRecording` | Plays start chime, brings window forward. |
| `Idle` | `Long Record` button clicked | `LongRecording` | Plays start chime. |
| `NormalRecording` | `Stop` button clicked | `Idle` | Plays end chime, flushes partial audio, copies final text to clipboard. |
| `NormalRecording` | Spacebar pressed while window focused | `Idle` | Plays end chime (via `stop_transcription`); same finalization. |
| `NormalRecording` | Global hotkey `Ctrl+Alt+Q` | `Idle` | Plays end chime; same finalization. |
| `LongRecording` | `Stop` button clicked | `Idle` | Plays end chime; same finalization. |
| `LongRecording` | Backend auto-timeout (180 s) | `LongRecording` → recording thread ends → text appears | **CONTRACT NOTE**: The current GTK code **does not** auto-transition the GUI state when the backend's 180 s timer fires. The GUI remains in `LongRecording` showing the placeholder; the user must still click `Stop`. The port **MUST** preserve this (do not add auto-stop detection in the GUI) unless Phase 3 explicitly re-specifies this. |
| Any | Window close (X) | `Idle` then process exit | Listener stopped, chime player cleaned up. |

### 3.3 Disallowed transitions

- **MUST** — Spacebar in `LongRecording` does **not** toggle stop (space is ignored in long mode). Only the `Stop` button (or global hotkey — see §3.4) exits long mode.
- **MUST** — Global hotkey `Ctrl+Alt+Q` while in `LongRecording` does **not** stop. (See `toggle_transcription`: it only stops if `recording_mode == "normal"`; in long mode, because `self.transcribing` is True, it falls through and does nothing.)
- **MUST** — Clicking `Start` or `Long Record` while already recording is a no-op (early-return in `start_transcription` / `start_long_recording`). This is also enforced visually by disabling both buttons.
- **MUST** — Clicking `Stop` in `Idle` is a no-op (early-return in `stop_transcription`). Also enforced visually.

### 3.4 Per-state widget enablement

| Widget | `Idle` | `NormalRecording` | `LongRecording` |
| --- | --- | --- | --- |
| `start_button` | enabled | disabled | disabled |
| `long_record_button` | enabled | disabled | disabled |
| `stop_button` | disabled | enabled | enabled |
| `transcription_view` | read-only, shows last final text (or empty on first run) | read-only, live-updated every ~30 ms | read-only, shows placeholder `"Recording in long mode..."` |
| `audio_indicator` | hidden | shown when `audio_detected`, hidden otherwise | shown when `audio_detected`, hidden otherwise |

### 3.5 Chimes on state entry

- **MUST** — On entry into `NormalRecording`: play start chime (C5-E5-G5 ascending, ~0.2 s). Driver: `ChimePlayer.play_start()`. Must play regardless of whether the trigger is button click, spacebar, or global hotkey.
- **MUST** — On entry into `LongRecording`: play start chime. Same sound.
- **MUST** — On entry into `Idle` *from any recording state*: play end chime (E5-C5-G4 descending). Driver: `ChimePlayer.play_end()`.
- **MUST** — Chimes are non-blocking (play on a background thread). The UI must not freeze while the chime plays. `ChimePlayer` already runs on its own thread; the port must not serialize chime playback on the GUI thread.
- **MUST** — Chime de-duplication: while a chime is playing, a second `play_start`/`play_end` call is a no-op (preserved by `ChimePlayer.is_playing` gate). Do not reimplement chime throttling in the GUI.

---

## 4. Keyboard & hotkey contract

### 4.1 In-window keyboard

- **MUST** — **Spacebar** toggles recording **only when the window has keyboard focus**:
  - In `Idle`: starts `NormalRecording` (plays start chime).
  - In `NormalRecording`: stops (plays end chime).
  - In `LongRecording`: **ignored** (no state change, no chime).
- **MUST** — Spacebar handling is suppressed while focus is in any widget that would otherwise consume space. In practice the only focusable interactive widgets are the three buttons and the read-only text view; none of them should consume space. **The port must ensure that pressing space with a button focused does not *also* click that button** — either by intercepting space at the window level before the button handles it, or by making buttons not respond to space activation. (Rationale: space activating a focused `Start` button would double-fire the start chime and transition; the GTK implementation handles this via window-level `key-press-event`.)
- **MUST NOT** — No other in-window shortcuts are defined. The port must not respond to Enter, Escape, Ctrl+C, Ctrl+V, etc., at the window level.

### 4.2 Global hotkey (pynput, works when window is not focused)

- **MUST** — Combo: `Ctrl + Alt + Q`. All three keys must be held down simultaneously. Either left or right Ctrl and either left or right Alt satisfy the combo.
- **MUST** — Fires on the **press** of `Q` while Ctrl+Alt are already held. Not on release.
- **MUST** — Semantics (mirrors `toggle_transcription`):
  - `Idle` → start `NormalRecording`, play start chime, **bring window forward** (raise, activate, focus).
  - `NormalRecording` → stop, play end chime, copy result to clipboard.
  - `LongRecording` → **no-op**. The hotkey does not stop long-mode recording. (Confirmed by reading `toggle_transcription`: the first branch guards on `recording_mode == "normal"`; the elif requires `not self.transcribing`, which is False in long mode.)
- **MUST** — Single-trigger: the Q key must re-rise before the combo can fire again. (Source resets `q_pressed = False` immediately after firing.)
- **MUST** — The global listener runs on a background thread; the actual GUI/transcriber actions must be marshaled to the GUI thread (see §6.3).
- **MUST** — When the app quits, the global listener must be stopped cleanly (`listener.stop()` in `on_destroy`).
- **MUST NOT** — No other global hotkeys. The port must not register global bindings for pause, cancel, volume, etc.
- **SHOULD** — Hotkey must work whether the app was launched from a terminal, shortcut, or auto-start. Windows requires no special entitlements for pynput, but note that pynput on Windows is less permission-sensitive than macOS — expect this to just work.

### 4.3 Keys that must NOT be responded to

- **MUST NOT** — Respond to `Alt+F4` in a custom way — let Windows deliver it as a standard close.
- **MUST NOT** — Respond to right-click / context menu in the transcription area with a custom menu. (Source has none.) The default OS text-view context menu (Copy) is acceptable, since the view is read-only.
- **MUST NOT** — Intercept system keys (Win, Ctrl+Esc, PrintScreen, etc.).

---

## 5. Clipboard & output contract

5.1 **MUST** — Auto-copy trigger: **exactly once per recording session**, at the moment recording stops (the transition into `Idle` from either `NormalRecording` or `LongRecording`). Not on partial updates, not on chime, not on start.
5.2 **MUST** — Copy payload: the full joined transcription — `"\n".join(transcriber.transcriptions)`. For long recordings, this is the single post-processing result. For normal recordings, it is the concatenation of all chunk transcriptions produced during the session.
5.3 **MUST** — The text area is also updated to this same joined content when recording stops, so what the user sees equals what is on the clipboard.
5.4 **MUST** — Clipboard target: the **system-wide clipboard** (Windows standard clipboard). On Linux the code uses `Gdk.SELECTION_CLIPBOARD` (not PRIMARY); on Windows there is only one clipboard, so this is the default.
5.5 **MUST** — **Silent overwrite**: the prior clipboard contents are replaced with no warning, prompt, or confirmation. (Current behavior; do not add a confirmation dialog.)
5.6 **MUST** — **Clipboard persistence after app exit**: GTK calls `clipboard.store()` to persist content after the app closes. On Windows the standard clipboard already persists across app exit without extra effort — no special action required.
5.7 **MUST** — On copy, log to stdout/logger at INFO-or-DEBUG: `Copied to clipboard: <first 60 chars>[...]`. Preserve this diagnostic (change `print` to `logging.info` is acceptable).
5.8 **MUST NOT** — No toast, tray balloon, status bar message, or audio cue on copy. The end-chime (§3.5) is the only user-visible cue that a session ended, and it is not specifically a "copy" cue.
5.9 **MUST** — Empty transcription: if `transcriber.transcriptions` is empty, the joined string is `""` and the clipboard is set to empty string (this overwrites prior clipboard contents with nothing). Do not add a "skip copy if empty" shortcut — match source behavior.

---

## 6. Threading contract

6.1 **MUST** — Single GUI thread. All widget creation, state reads, and state writes (text area content, button enabled state, indicator visibility, window raise/focus) happen on the GUI thread. No exceptions.

6.2 **MUST** — GUI polling timer: while a recording is active, a GUI-thread timer fires every **30 ms** (≈33 Hz) and performs:
  - read `transcriber.transcriptions` and re-render the text area (normal mode) or keep the placeholder (long mode);
  - read `transcriber.audio_detected` and show/hide the indicator;
  - stop itself when `self.transcribing` becomes False.
  The timer must not run while `Idle`. The 30 ms cadence is intentional for smooth audio-indicator responsiveness; do not slow it to 100 ms to "save CPU" — the feel depends on it.

6.3 **MUST** — Cross-thread signaling: three sources produce events on non-GUI threads and each must be marshaled to the GUI thread before touching widgets:
  - **Global hotkey listener** (pynput) — dispatches on its own listener thread; must post the toggle action to the GUI thread (GTK uses `GLib.idle_add`; the PyQt6 port must use the equivalent cross-thread dispatch mechanism, e.g. signal/slot with a queued connection, so that widget work runs on the GUI thread).
  - **Recording thread** (inside `RealTimeTranscriber.record_loop`) — appends to `transcriber.transcriptions` and mutates `audio_detected` on its own thread. The GUI must never reach into these attributes from a non-GUI thread; it reads them only via the 30 ms timer running on the GUI thread. Reads are intentionally lock-free; tolerate a one-tick staleness.
  - **Chime player thread** — self-contained, never touches widgets. No marshaling needed.

6.4 **MUST** — Clean shutdown on window close:
  - stop the global hotkey listener;
  - stop the 30 ms GUI timer (if running);
  - stop the recording thread (if running — treat as implicit stop, but do not auto-copy to clipboard on shutdown; source does not do this);
  - terminate `ChimePlayer` (releases the PyAudio instance);
  - terminate the GUI event loop.

6.5 **MUST** — No `time.sleep` or other blocking calls on the GUI thread anywhere. All waiting happens via timers or worker threads.

6.6 **MUST NOT** — Do not share Whisper inference or PyAudio streams across threads. They live in the recorder thread only.

---

## 7. Linux-specific behaviors NOT to preserve

7.1 **MAY drop** — Custom GTK `HeaderBar` with embedded close button. Use native Windows title bar (§1.11). Do not recreate a custom title bar on Windows — it would clash with OS conventions and cost implementation effort for no user benefit.
7.2 **MAY drop** — GTK CSS provider and class-based styling. Reimplement the exact colors (#00FF00, #FF0000, #0000FF, #00AA00) using PyQt6's styling mechanism of choice; do not attempt to preserve the CSS pipeline.
7.3 **MAY drop** — `.desktop` file, `nohup` invocation, XDG autostart. Windows equivalent: a Start Menu shortcut and/or a `.lnk` in `shell:startup` for autostart. Neither is a GUI contract item; whoever packages the Windows build can decide. Not required for Phase 2.
7.4 **MAY drop** — X11 / Wayland display detection. PyQt6 on Windows targets the WinAPI backend transparently.
7.5 **MAY drop** — `Gdk.SELECTION_CLIPBOARD` vs `SELECTION_PRIMARY` distinction. Windows has only the standard clipboard.
7.6 **MAY drop** — The `print("[DEBUG] Copied to clipboard: ...")` literal string (replace with `logging.info`; content of the message should remain roughly equivalent for grep-ability).
7.7 **MUST NOT** drop — Always-on-top, opacity 0.9, 650x200 default size, 30 ms polling cadence, chime timing, global hotkey combo, per-mode state-machine quirks (space ignored in long mode; global hotkey ignored in long mode). These are the behavioral fingerprint of the app on Linux and must be preserved bit-for-bit on Windows.

---

## 8. Summary of conformance flags

Counts are maintained for traceability:

- Explicit **MUST** items: 60
- Explicit **SHOULD** items: 5
- Explicit **MAY drop** items: 7

If any **MUST** in this document conflicts with the meta-plan
(`WINDOWS_PORT_PLAN.md`), raise the conflict before coding; do not silently
deviate.
