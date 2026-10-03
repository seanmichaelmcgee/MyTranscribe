# Day findings 2026-10-03: speed, model size, formatting, UI

Local GTX 1660 Ti session, synthetic and fictional audio only (Windows SAPI voices through
simulated headset / Tenor-style conference / noisy-room mics). Raw logs stay in the
gitignored `results_overnight/` folders.

## TL;DR
1. **New default: large-v3, greedy (beam 1), int8_float32, 20 s chunks.** Best accuracy
   of everything tested, and short snippets come back about **1 s** after Stop (turbo:
   ~0.65 s); 20-60 s dictations ~1.3-2.5 s. Turbo stays one click away (Options →
   Accuracy → Fast).
2. **Spoken formatting works** ("new line", "new paragraph", "open quote … close quote"):
   10/10 messages correct with beam 1. Beam 5 silently dropped the command words in 4/10,
   one more reason to use greedy.
3. **GTX 16xx should use int8_float32**: 26-29 % faster than int8_float16 in alternating
   runs, same accuracy (no tensor cores on TU116).
4. small.en / medium.en are not worth it here: faster by a few hundred ms, clearly worse.
5. UI: compact always-on-top window, green/red recording light, F9 hold-to-talk, mouse
   forward button toggle, Options screen, verified copy (never pastes stale text),
   Long record removed (one button handles up to 1 h).

## 1. What a clinician feels: Stop → text on the clipboard
Measured with the real pipeline (`scripts/latency_bench.py`): audio fed at 2× real time,
Stop pressed after D seconds, mean of 3 runs (seconds). The worker never fell behind
(max queue 0-1) in any run.

| model (int8_float32) | beam | chunk | 5 s | 10 s | 20 s | 30 s | 45 s | 60 s |
|---|---|---|---|---|---|---|---|---|
| small.en | 5 | 30 s | 0.57 | 0.67 | 0.89 | 1.28 | 0.92 | 0.78 |
| medium.en | 5 | 30 s | 0.90 | 1.16 | 1.54 | 1.76 | 1.46 | 1.15 |
| large-v3-turbo | 5 | 30 s | 0.90 | 0.94 | 1.21 | 1.87 | 1.15 | 0.80 |
| large-v3 | 5 | 30 s | 1.37 | 1.56 | 2.56 | 4.14 | 2.30 | 2.99 |
| large-v3 | 1 | 30 s | 1.13 | 1.41 | 2.00 | 3.11 | 2.05 | 2.78 |
| **large-v3 (new default)** | **1** | **20 s** | | **1.46** | **2.49** | **1.64** | **1.28** | **2.41** |
| large-v3 | 1 | 15 s | | | 1.15 | 1.40 | 1.29 | 1.37 |

(20 s / 15 s chunk rows: mean of 5 runs. Snippets shorter than one chunk don't depend
on chunk length: large-v3 greedy averaged 0.97 s over all 54 snippet clips, worst 1.33 s.)

**Why the 30 s column is the worst:** text is transcribed in chunks *while you talk*.
After Stop, only the unfinished chunk is left. A dictation that ends just before a chunk
would have been cut leaves almost a full chunk to do after Stop. Shorter chunks shrink
that worst case; short snippets (< one chunk) are always transcribed whole after Stop,
so for them only model speed matters.

**Against your budget** ("+2 s on a 10 s note is too much; fine on 30-60 s"):
large-v3 adds ~0.5 s over turbo on a 10 s snippet (1.41 vs 0.94 s), and with the new
20 s chunks stays around 1.3-2.5 s for 20-60 s dictations (15 s chunks: ~1.2-1.4 s, but
no accuracy gain; see below). The worst case is a dictation that ends just as a chunk
fills (e.g. exactly 20 s), when the whole chunk is left to do after Stop.

**Open item:** two isolated slow cases were seen across ~200 timed sessions (13 s and
7.4 s after Stop). Re-running the same conditions 20+ times, with per-chunk timing and
with Whisper's temperature fallback switched off, did not reproduce them. Likely another
process using the GPU at that moment. The new per-chunk output cap bounds how long one
chunk can ever take. Worth watching in real use: if the status sits on "Transcribing…"
for more than ~3 s, note what else was running.

## 2. Accuracy by model

### Letters / long dictation (40 files: 10 FM/IM/peds dictations × 4 mics, topic prompts + correction)
| model (int8_float32) | beam | WER % | term recall % | compute (RTF) |
|---|---|---|---|---|
| small.en | 5 | 9.0 | 72.7 | 0.033 |
| medium.en | 5 | 6.3 | 75.4 | 0.071 |
| large-v3-turbo | 5 | 5.6 | 78.1 | 0.044 |
| large-v3 | 5 | 5.0 | 84.6 | 0.119 |
| **large-v3** | **1** | **5.0** | **83.1** | **0.084** |
| **large-v3, 20 s chunks (new default)** | **1** | **4.5** | **85.8** | **0.097** |
| large-v3, 15 s chunks | 1 | 5.1 | 81.9 | 0.110 |

Chunk-length differences (15 / 20 / 30 s) are within the noise of 40 files, but both
this and the fixed-cut test below lean towards 20 s.

Noisy room is the weak spot for every model (large-v3: ~7.5 % WER, ~72 % terms; small.en
falls to 51 % terms).

### Short snippets, your three workflows (27 snippets × headset + conference, `scripts/eval_snippets.py`)
| setting | messages WER / terms / format | results WER / terms | exam WER / terms | wait mean / max |
|---|---|---|---|---|
| small.en b5 | 2.0 / 100 / 8 of 10 | 11.4 / 85.0 | 3.2 / 93.8 | 0.34 / 0.47 s |
| medium.en b5 | 5.4 / 95 / 3 of 10 | 5.7 / 95.0 | 7.4 / 100 | 0.69 / 0.94 s |
| turbo b5 | 1.3 / 95 / 10 of 10 | 3.4 / 92.5 | 6.4 / 97.9 | 0.65 / 0.86 s |
| turbo b1 | 1.3 / 95 / 10 of 10 | 3.4 / 92.5 | 6.4 / 97.9 | 0.63 / 0.72 s |
| large-v3 b5 | 0.3 / 100 / **6 of 10** | 2.3 / 95.0 | 4.3 / 93.8 | 1.14 / 1.61 s |
| **large-v3 b1** | **0.3 / 100 / 10 of 10** | **2.3 / 95.0** | **4.3 / 93.8** | **0.98 / 1.41 s** |

"Format" = the line breaks and quotes in the written text came out right.

## 3. Is formatting by voice feasible with Whisper? Yes, with greedy decoding
Whisper writes spoken commands out as words ("…any spot. New line. Open quote. Follow-up
X-ray. Close quote."), and `voice_commands.py` turns them into formatting. To avoid eating
real words, a phrase only counts as a command when Whisper set it off with punctuation, so
"start a new line of therapy" stays text. Turbo and large-v3 greedy: 10/10. Large-v3
beam 5: 6/10, because beam search sometimes **deletes the command words** as if they were
disfluencies (word error rate didn't move because the expected text doesn't contain them).
That, plus equal accuracy and ~30 % less compute, is why the default is now beam 1.

Your example, as transcribed by large-v3 greedy through the conference mic:
`Please call and tell him his X-ray is normal and book review in 2 weeks, any spot.`⏎
`"Follow-up X-ray".`

## 4. Compute type on the GTX 1660 Ti
Alternating order, 6 runs per cell, ~3 min of audio each (RTF, lower is faster):

| model | int8_float16 | int8_float32 | peak VRAM (whole card, f32) |
|---|---|---|---|
| large-v3-turbo | 0.088 | **0.063** | 2.4 GB |
| large-v3 | 0.153 | **0.113** | 3.9 GB |

`hw_profile` now gives int8_float32 to GTX 10xx and 16xx; RTX cards keep int8_float16.

## 5. Chunk length vs accuracy (turbo, fixed cuts, clean/conference)
10 s: 11.3 / 13.1 % WER and 2.5× the compute (Whisper always processes a 30 s window);
15 s: 10.2 / 10.9; 20 s: 9.4 / 10.7; 30 s: 9.0 / 10.0. (Fixed cuts exaggerate the
damage; the app cuts at pauses, where 20 s scored *better* than 30 s for large-v3.) So:
never below 15 s.

## 6. Robustness changes made today
- **Verified copy.** If another program holds the clipboard, the copy is retried ~0.5 s,
  then the window says "Not copied — click Copy" and nothing is auto-pasted. The
  clipboard is re-checked right before any auto-paste. (Last night's run showed the old
  code would have pasted the *previous* clipboard contents.)
- **Output cap per chunk** (`fw_engine.max_new_tokens`): at most ~10 tokens per second of
  audio, within Whisper's 448-token window. Stops runaway loops/hallucinated repeats
  from filling a note (and from stalling the text for many seconds).
- **Non-blocking clipboard check.** The first GUI stress run with the new window showed
  470 ms UI stalls whenever the clipboard was busy: Qt's clipboard *read* blocks ~0.6 s
  retrying while another program holds it. The copy check now uses Windows'
  clipboard sequence number (never blocks) and only reads back once it has changed.
  GUI stress afterwards (large-v3, 20 hotkey cycles, every copy failing in this
  sandbox): worst stall 73 ms, p99 13 ms, **0 pastes after a failed copy**.
- Hold-to-talk press never stops a recording started another way; only the release does.
- Default chunk length 30 → 20 s; default beam 5 → 1.
- Tests: 172 (all pass from a normal terminal; the one real-clipboard test fails only
  inside the Claude session, which has no clipboard access).

## 7. Deterministic "hints" (in use, and what's next)
In use now, all deterministic and offline:
- **Topic-aware prompts**: each chunk's Whisper prompt carries terms for the topics being
  dictated (21 topics, ~1,150 terms), rotated within Whisper's ~223-token limit, plus the
  last ~160 characters of transcript for context. New today: **exam shorthand** (SNT, NAD,
  HEENT, TMs, JVP, CVA tenderness, soft non-tender…) and **results shorthand** (CBC,
  lytes, eGFR, INR, TSH, A1c…).
- **Spelling correction** of near-miss non-words to vocabulary terms (never real words,
  never ALL-CAPS/short words, unique close match only).
- **Voice commands** for layout.

Worth adding next (cheap, deterministic, no new dependencies):
1. **Your own vocabulary file** from your real letters: colleague names, clinics, drugs
   you use, phrases you repeat. Highest expected gain for letters. (`MYTRANSCRIBE_VOCAB_FILES`
   already supports it.)
2. **Per-workflow style examples**: the prompt's style example is letter-like. A terse
   example ("Abdomen SNT. CVA tenderness. Renal normal, Hb similar.") for short
   dictations should nudge Whisper toward your shorthand. Pick by length so far, or by the
   first words. Needs an A/B on the snippet set.
3. **Sanity flags (highlight, never change)**: drug + dose with an implausible unit
   ("metformin 1000 g"), a dose with no unit, left/right both in one sentence,
   numbers that look mis-heard ("5.4" vs "five for"). Shown as a yellow underline in the
   window before you paste.
4. **Low-confidence highlighting**: Whisper reports a probability per word. Underlining
   words below a threshold shows where to proofread, deterministically and cheaply.

## 8. Local LLM reviewer: assessment
**Recommendation: not now.** Revisit for letters only, as an optional "polish" step,
after items 7.1-7.4.

- **Fit on this PC.** large-v3 uses ~3.2 GB of the 6 GB card. A useful local LLM (3-4 B
  parameters, 4-bit) needs ~2.5-3 GB plus working memory, so it would not fit beside
  large-v3 on the GPU (beside turbo, just about). On the i7-9700 CPU it would run at a
  few tokens per second: roughly 3-6 s to review even a short snippet, which breaks the
  ~1 s budget for messages and results.
- **Safety.** An LLM that rewrites clinical text can invent or "correct" content
  plausibly (a dose, a side, a negation), which is worse than an obvious ASR error. Any
  reviewer must only *flag* words, never change them silently, and its flags would need
  their own testing.
- **Leanness and security.** It would add a native inference library and a multi-GB
  model file to an app whose point is to be small and auditable.
- **Where it could pay off:** long letters, where an extra few seconds is fine and
  style matters ("make this read like my letters"). Shown as a side-by-side diff the
  user accepts. That is a separate, later build.

## 9. Recommended next steps
1. Real-mic test with your Bluetooth headset: read a few snippets of each type and two
   letters; compare against these synthetic numbers (SAPI voices are cleaner and slower
   than real speech).
2. Collect 5-10 of your typical letters (de-identified) → personal vocabulary + style
   example.
3. A/B a terse style example for short dictations.
4. Sanity flags and low-confidence underlines (7.3-7.4).

## Timeline
- 08:15 Sweep started (compute A/B, large-v3 accuracy, chunk lengths). UI and safety work
  in parallel; all pushed to PR #4 as separate commits.
- 09:00 int8_float32 for GTX 16xx and the Best/Fast accuracy option pushed.
- 09:20-10:05 Latency by model size; snippet set (three workflows); small/medium accuracy.
- 10:05-10:45 Round 2: large-v3 beam 1 on letters, chunk 20/15 latency.
- 10:58-11:18 Round 3: default engine sanity (beam 1 + output cap: identical results, no
  errors), chunk 15 accuracy, chunk 20/15 latency (5 runs each).
- 11:25-11:45 Slow-case hunt (not reproduced); 20 s chunk default; GUI stress found and
  fixed the clipboard read stall.
