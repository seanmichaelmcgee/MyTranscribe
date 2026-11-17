# Typing as you dictate: measured and fixed (2026-11-17)

Options → "Type into my document while I dictate" pastes text at the cursor while you keep
talking; the full text is also copied at Stop. Until now it had never been measured. This round
compared what it types with what Stop copies, on every recording of the owner that has a script,
and tried shorter audio windows so text appears sooner.

## How it was measured

`scripts/live_insert_bench.py` runs each recording through the app pipeline once (Whisper
large-v3, the owner's "personal" profile: pause-aware, spoken punctuation, only dictated commas,
medical clean-up) and builds three texts from the same run:

- **copied**: the whole transcript formatted at Stop (what the app copies);
- **typed**: what the app now types (below);
- **old typing**: what it typed before this change (each piece formatted on its own).

All three are scored against the script. Timing is replayed on a real-time clock from the
measured decode times on the RTX 4070 Ti SUPER. 54 recordings, 19.3 minutes, 2,855 words: 23 older
held-out recordings, the 26-item reading of set v1 and the 5-item letters of set v2.
`scripts/live_insert_rescore.py` re-types saved runs with changed rules, without recognition.

## What was wrong, and the fix

Each finished piece was formatted on its own and pasted with a space before it. Three things
depend on what comes after a piece and were lost:

1. A spoken "new paragraph" at the end of a piece had nothing after it yet, so the break fell
   off and the next piece followed after a space: **paragraphs and lists were lost in 14 of the
   24 recordings that have them**.
2. A hesitation "..." could not be cleaned up before the next word arrived.
3. A full stop the model wrote at the end of a piece, where the next piece starts with a spoken
   "comma", was typed as a full stop ("Okafor. a 71-year-old").

Now (`src/live_insert.py`) the whole transcript so far is formatted exactly as the copy at Stop
is, and only the new part is typed. The trailing break, "..." or last punctuation mark is held
back until the next piece shows what follows (it appears with the next piece, or at Stop). If
formatting ever changes something already typed, typing carries on after the same number of
words, so nothing is typed twice.

| 30 s windows, 54 recordings | Old typing | Typing now | Copied at Stop |
|---|---|---|---|
| Word errors | 2.35% | 2.35% | 2.35% |
| Layout right (24 with paragraphs or lists) | 10 / 24 | **24 / 24** | 24 / 24 |
| Recordings where typed text differs from copied | 15 | **0** | - |

## Shorter windows: text sooner, at a cost

The app decodes audio in windows of up to 30 s; with pause-aware dictation an unfinished last
sentence (up to 6 s) is carried into the next window. Shorter windows give text sooner:

| Window | Word errors | Layout | New text appears about every | After the piece's audio ends | Stop → last text |
|---|---|---|---|---|---|
| 30 s (before) | **2.35%** | 24 / 24 | 19 s | 0.9 s | 0.5 s |
| **15 s (now, when typing)** | **2.91%** | 24 / 24 | **6 s** | 0.5 s | 0.4 s |
| 20 s, carrying up to 10 s | 3.05% | 23 / 24 | 7 s | 0.6 s | 0.5 s |
| 16 s, carrying up to 8 s | 3.61% | 23 / 24 | 5 s | 0.5 s | 0.4 s |
| 10 s | 6.62% | 20 / 24 | 3 s | 0.4 s | 0.4 s |
| 5 s | 22.7% | 12 / 24 | 1.5 s | 0.3 s | 0.3 s |

By set, 30 s → 15 s: held-out 2.86% → 3.47%, reading 2.08% → 2.50%, letters 1.22% → 2.13%.

- Carrying longer sentences did not help: the cost comes from Whisper hearing less speech at
  once, not from sentences being cut.
- **Adopted:** 15 s windows only while "Type into my document while I dictate" is on
  (`gui_med.LIVE_INSERT_CHUNK_S`). Copy-at-Stop keeps 30 s windows and its accuracy. With 15 s
  windows the typed text again matched the copied text in all 54 recordings.
- Compute rises by half (72 s → 107 s for 19 minutes of audio on this card), still about a tenth
  of real time; a 6 GB card should keep up but was not measured.

## Limits

- Replayed timing, not a live session: the clock is real decode times plus the audio's own
  length. Pasting into an EMR adds its own delay (0.3 s between pastes in the app).
- One speaker, read scripts. A dictation full of long pauses commits text at the same rate
  (a window is cut by length), so text can still lag a sentence that is still being spoken.
- Not exercised against a real EMR window in this round; the clipboard and focus rules are
  unchanged and covered by the unit tests.
