# Local dictation accuracy specification — 4 October 2026

This iteration targets brief results/messages, clinical examinations and 30–60 s
letters. Medical values, medications, negation and correction effort take priority
over aggregate word error. The five reviews support one initial prompt experiment;
they do not support a decoder, gain, VAD, model or UI default change. The saved
30-clip corpus and both phone files are calibration, not clinical validation.

Campaign start: 17:35:31 UTC; fixed cutoff: 19:35:31 UTC (16:35:31 Halifax).
Use the existing branch and PR #4. Detailed evidence and resume state remain in
`results_1060/accuracy_program_20261004`; every worker has its own findings,
scratchpad, status and evidence files. Do not extend original deadlines on resume.

## Flow and ownership

| Stage | Required behavior and boundary |
|---|---|
| Capture | Ready microphone, nominal 0.512 s memory pre-roll, 16 kHz mono int16 and 1024-frame reads. Preserve delivered quiet frames. Ordinary clinical audio stays in memory; fictional-test archival is explicit and separate. Device readiness/reconnect/onset need live verification. |
| Input feedback | Recording state is separate from speech/activity. Meter describes the exact model-input scaling before speech filtering. A future transform requires post-transform metering and numeric pre/post diagnostics; do not imply fidelity from a moving meter. |
| Chunk scheduling | One 30 s pause-aware workflow; quietest 30 ms frame in final 5 s, remainder retained. Stop immediately flushes a short remainder. The whole-chunk RMS gate and Whisper VAD are distinct. No second mode until measured benefit exceeds interaction cost. |
| Recognition | Baseline: local large-v3 snapshot `edaa852ec7e145841d8ffdb056a99866b5f0a478`, CUDA int8_float32, beam 5, patience 2, two CPU threads, English. Experiments refuse silent device/precision fallback and new downloads. |
| Context | Bound complete prompt to 215 tokens. Style, selected vocabulary and previous postprocessed text are explicit conditioning. Runtime `condition_on_previous_text=False` does not disable application context. References never enter recognition. Future reviewer guesses cannot enter acoustic context silently. |
| Correction | Preserve raw, filtered and cleaned tracks. Exact non-word spelling changes require whole-word/unique-match safeguards. Do not infer numbers, real-word clinical substitutions or negation. Spelling improvement is distinct from acoustic improvement. |
| Formatting | Interpret explicit supported commands/native markup; preserve unknown/damaged spans and unresolved ages. Check association of paragraphs/lists with content, not only counts. Do not rewrite prose or invent placeholders' values. |
| Optional review | Keep original text and expose every proposed material edit. Transcript-only review cannot recover an unheard number with certainty. No installed local reviewer model is available for an authorized new trial; no new weights/packages or cloud reviewer in this campaign. |
| UI/output | Retain compact Windows UI, F9 hold, mouse-forward toggle, green recording/red idle state, expandable debugging and binding options. Clipboard remains acceptable. Keep `src/gui_qt.py` behavior unchanged; file replay/headless tests do not establish native copy/paste. |

## Integrated evidence and ranked implementation order

| Priority / avenue | Evidence, mechanism and falsifiable next step | Cost and rejection rule |
|---|---|---|
| 1. Remove reusable patient facts from style | Both isolated ~3 s phone results copy the numeric/name-bearing example. CPU trace: 82 tokens fully retained, so this is not prompt truncation. Test the exact 53-token replacement at all durations, preserving its existing medical lexical items, topics/context and all other controls. This differs from rejected <=5 s minimal-style policy. | One inference call; no new memory/dependency. Fewer tokens do not establish speedup. Reject for new critical errors, unresolved copying, old-corpus medical/common loss or unacceptable timing. Retained medication terms may still insert. |
| 2. Context/rotation reproducibility | GUI and normal trial reuse a builder; rotation changes 5/74 later reconstructed prompts over two passes, with no first-chunk differences. A future two-config persistent-versus-reset rotation test holds waveform and decoder fixed and observes later raw changes. | Small CPU state reset, unknown recognition/timing effect. Leave default unless later-chunk clinical benefit and first-chunk invariance are measured. Raw-only context is also untested and can lose beneficial spelling context. |
| 3. Faithful long MedASR context | Basic CTC merging passes 300 exhaustive CPU cases. Top16→64 weak-LM pruning changes 0/11 verified cached phone outputs. Official per-piece LM convention is intentional. Better justified future avenue: 20 s/18 s Hann posterior fusion, rather than another alpha/beta sweep. | About 1 MB float32 logits per 20 s window; extra overlap calls/buffering, unknown finishing delay. Validate actual masks/time alignment (497 valid frames locally), fuse probabilities rather than raw logits, reject boundary omissions/duplicates or new critical errors. No current production fix. |
| 4. Actual whisper/capture | 011 is 2.85 dB quieter but phonation is unconfirmed. All eight inputs pass RMS gate; VAD bypass previously leaves three isolated transcripts identical. Peaks near full scale mean +3 dB would clip both whole files. Capture buffers quiet frames. | No gain/VAD change now. Collect paired true whisper/normal audio per device. Later attenuation is a level diagnostic; gate-only bypass requires demonstrated speech being skipped plus blank/noise controls. Reject hallucinated noise, critical loss or clipping. |
| 5. Formatting and separate review | MedASR age placeholders and damaged markup remain unresolved; count matches cannot certify structure. Old medical/common rates omit insertion-specific errors. | CPU explicit-command fixtures and per-edit review first. No real-word/number/negation repair from these samples. A future local reviewer needs separately authorized existing-compatible weights, measured RAM/VRAM/delay and anti-feedback policy. |

Whisper prompt/hotword channels are preceding decoder text, not instruction-following
or constrained labels. The installed fresh-window CPU test gives identical token
IDs for equivalent short content in either channel; earlier broad hotword tests
did not solve HGB. Prompt-echo flags also flag hypothetically genuine matching lab
values, so they can prioritize review but must preserve text. Confidence/fallback
metrics passed the observed copied output and cannot certify clinical correctness.
Mechanisms: [pinned faster-whisper source](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py),
[Whisper generation API](https://opennmt.net/CTranslate2/python/ctranslate2.models.Whisper.html).

Google's reference intentionally makes sentence pieces decoder words. The only
official MedASR checkpoint found is the 105M v1.0 model; GPU headroom supplies no
evidence of a larger model. Published normalization removes de-identification
spans/voice commands and therefore does not establish age/format fidelity.
[Official quickstart](https://github.com/Google-Health/medasr/blob/main/notebooks/quick_start_with_hugging_face.ipynb),
[model card](https://developers.google.com/health-ai-developer-foundations/medasr/model-card),
[MedASR paper](https://arxiv.org/html/2605.16555v1).
True whisper differs spectrally from reduced-level voiced speech;
[primary whisper study](https://personal.utdallas.edu/~john.hansen/Publications/CP-Interspeech11-AnalysisWhisper-FanGodinHansen-IS110425.PDF).

## Reference and evaluation contract

Keep original inference JSON/manifests and historical intended-script scores
unchanged. Human-confirmed spoken BP is **132/78 in 010, 138/78 in 011**; neither
correctly recognized value is an ASR failure because it differs from a script.
The earlier 132/72 feedback remains preserved history and is superseded.

The supplied formatted Frontier transcript is a separate comparator, with unknown
upstream model/settings/command handling and no claimed local listening. All
non-BP words retain external-model authority. Raw comparison to formatted external
text is agreement, not spoken WER. Preserve literal lexical disagreement alongside
predeclared notation equivalence and separately anchored clinical fields:

- BP slash/over notation; age; medication-name/dose/unit/frequency tuples.
- H G B/HGB and E G F R/eGFR; attached normal/similar-to-prior modifiers.
- Changed/change from prior and exam/examination in this exam context; Romberg
  unchanged and no nystagmus as separate assertions.
- Pain-at-rest/syncope/palpitations negative scope, ECG without acute ischemic
  changes and exertional chest discomfort; all new critical insertions/omissions.
- Paragraph association and unknown native tokens. Phone samples have no numbered
  clinical list, so numbering-count success is vacuous.

Names are excluded using independently supplied metadata; medical eponyms remain
scored. Exact counts/denominators, per-workflow raw/cleaned changes and all edit
alignments accompany aggregate WER. Finite field regexes are review signals,
not clinical entailment. Crops, whole files and repeats remain correlated views
of two recordings. Reserved personal packet 09/12/13 stays unused for tuning.

Supplemental saved-output review validated 17 runs and excluded one stale-source
010 artifact. Current isolated Whisper notation disagreement is 9/112 words for
010 and 14/112 for 011; all 34 raw/cleaned BP views match human values. These are
external formatted agreement findings, not a revised clinical accuracy rate.

The historical replay performs an int16→float32/32768→int16*32767 roundtrip.
CPU diagnostics found <=1 LSB differences and a 30 ms pause-cut shift on one
letter. The initial A/B preserves that route and records effective PCM and pre-VAD
chunk hashes. It cannot be labeled sample-exact live capture. Model loading,
offline compute, cached decoder work, paced Stop-to-formatted text, speech-end
tail, GUI polling and clipboard transfer are separately labeled timing categories.

## Independent development comparator queue

Human steering permits remote transcription only for expressly supplied fictional
development recordings. Ordinary clinical capture stays local/offline. The original
chat prepared a durable SQLite queue and bounded worker; this coordinator owns
tested tracked integration in `scripts/frontier_audio_queue.py` and
`scripts/frontier_audio_worker.py`. Reuse the existing ignored queue through
`--root`; do not duplicate its two jobs or mutate the legacy pasted references.
For these jobs the exact argument is
`--root results_1060/accuracy_program_20261004/frontier_bridge/data`.

The proposed API route is `gpt-transcribe` at `/v1/audio/transcriptions`, with
25 MB input bounds, supported audio formats, verified TLS/no redirects and stdlib
HTTP only. [Official file transcription documentation](https://developers.openai.com/api/docs/guides/speech-to-text).
Provider/account selection and secure key setup remain pending in the original
chat. No request or background uploader is launched by this campaign, and API
model access/end-to-end behavior remains untested. This API alias is not asserted
to be the model behind the supplied ChatGPT results or a Codex model.

Blind requests contain model/file fields and generic filenames only, no scripts,
local candidates, expected values, vocabulary or feedback. Queue keys include
audio bytes, requested model and protocol. Retain approved original bytes,
request/result IDs, UTC timestamps, attempts, literal returned JSON/hash and
returned model identity; resolved snapshot remains unknown without verification.
No key enters code, disk metadata, logs or command arguments. Missing auth blocks
all pending jobs without network. A key's presence alone is not a provider-choice
decision; the operator must select and explicitly execute the route.

Success is immutable. Interrupted uploads become uncertain unless a saved response
matches audio/model/protocol and contains a valid transcript. Explicit retry must
acknowledge a possible duplicate; no automatic retry/charge. Model/protocol drift
fails visibly. Watch/request singleton locks, fixed <=120 min original session
deadline, finite request budget, <=120 s owned-child bound and STOP file keep
processing observable and stoppable independently of chat quota. Cleanup targets
only the created child tree. No startup registration, scheduler or daemon is
installed; disk persistence does not imply continuous operation. Two prepared
jobs remain `blocked_auth`, zero attempts. Manual ChatGPT imports remain a separate
provenance route if that is the user's choice.

## Acceptance and next independent capture

No new silent critical field error is acceptable. Preventing example copying on
both crops is necessary but an HGP/HGV abbreviation or uncertain result is still
wrong. Require old-corpus medical/common and semantic formatting preservation.
Promote only matched, source/model/runtime/audio/reference-verified evidence and
relevant passing tests; retain unsupported adapters outside the ordinary app.

Proposed timing aspirations: warm median <=0.5 s / p95 <=1 s on <=10 s tasks and
median <=2 s on 30–60 s letters. These exact numbers are not user-approved promises;
report measured distance. About two extra seconds on a brief instruction conflicts
with the stated workflow. One phone cell cannot establish a timing distribution.

For capture calibration, freeze three new independent fictional scripts across
result, exam and letter; capture normal/true-whisper pairs on headset,
conference/Tenor-like mic and PowerMic: 18 files, nine correlated pairs. Record
actual device/connection/default endpoint/host API, rate, input level/processing,
distance/angle/room, keep-ready and phonation confidence. Counterbalance order,
preserve pre-roll/tail, mark actual speech onset/end and deviations independently
of outputs. After selection, use new held-out utterances (at least 12 files for
one short/long per device/phonation) plus a larger ~20-per-workflow independent
set before broad claims. Split by utterance/session so pairs/crops cannot leak.
Include varied ages, BP, doses/units/frequencies, numeric and nonnumeric labs,
positive/negative assertions, eponyms and real paragraph/list/quote intent.
Measure readiness, end-of-speech→Stop, formatted output and actual copy/paste
separately. These sample counts support exploration, not clinical reliability.
