# MedASR native-format investigation — 2026-10-04

## Scope and result

This change is confined to the opt-in deterministic formatter, its unit tests,
and this report. No production `src` files, recognition settings, model inputs,
or decoder code were changed. No inference, GPU work, package installation,
commit, or push was performed. The existing `--medasr-format native-v1` opt-in
remains the entry point; reverting the formatter file reverses the behavior.

Mixed valid command cases improved from **23/35 to 35/35** after the existing
final `voice_commands.apply` pass. The **370 saved MedASR utterances all render
identically before and after**. Consequently this change demonstrates a
formatting repair and no measured improvement in saved recognition accuracy.

## Evidence and diagnosis

Read `CLAUDE.md`, `LOCAL_SESSION_HANDOFF.md`, the ignored saved runs under
`results_medasr/overnight_native_20261003`, their scorecards, and the local
`results_1060/real_headset/manifest.json`. References were used only to diagnose
and count formatting errors. They were never passed to a model or formatter.

The saved real-headset cleaned scorecard reports WER 11.2%, medical WER 4.1%,
format counts 29/30, numbering 28/30, five numeric review signals, and zero
negation review signals. Those are historical measurements, not a new paired
evaluation. Its two numbering failures are:

- `27_letter__real.wav`: recognition produced `newline}` without the opening
  brace. There is no valid layout command before the first item.
- `29_letter__real.wav`: recognition produced `wo {period}` instead of a valid
  number word. Guessing the intended number would conceal a recognition error.

Both remain visible. The five-repeat and three-repeat saved runs repeat these
same failures. Synthetic snippet and test-dictation saved scorecards already
report full format and numbering counts. No valid spoken layout phrases were
found in the saved raw outputs, so the new mixed-command behavior needs separate
general command tests rather than claims of corpus accuracy improvement.

## Implemented formatting policy

- Resolve exact native layout markers and set-off spoken `new line`, `next
  line`, and `new paragraph` before converting native numbered items. Actual
  existing line breaks also establish item boundaries.
- Native item numbers and the optional `number` prefix are case insensitive;
  native brace marker spellings remain exact and case sensitive.
- Recognize singular spoken `period`, `full stop`, and `dot` at line starts when
  accompanied by an explicit `number` prefix or punctuation after the command.
  Bare `one period of pain` stays prose in the adapter.
- Spoken layout needs punctuation, a text/line boundary, or an exact preceding
  native `{period}`. With only a left boundary, grammatical continuations such
  as `of`, `in`, and `for` leave the phrase as prose. Commands are not recovered
  through fuzzy matching or inferred list sequencing.
- Preserve unknown brace contents during spoken command parsing, whitespace
  cleanup, and the supplied postprocessing callback, including multiline spans.
  No clinical spelling or numerical conversion rules were added.

The ordering repair covers general input such as `Plan. New line. One {period}
Review`, which previously ended with `One. Review` after the final shared pass
and now ends with `1. Review`. Native and spoken commands can be interleaved in
one utterance.

## Verification and iterations

The baseline formatter was loaded in memory from `git show
HEAD:scripts/medasr_native_format.py`. Its SHA-256 is
`57f8ed667c8a53c99ed62616e061c08bcb90eb3c7008c3236dbcdee4d51e2a1f`,
matching the recorded formatter fingerprint in all five saved MedASR runs.
No saved result file was rewritten and no source-fingerprint validation was
bypassed to present an old run as a new run.

| Saved run | Utterances | Formatter output changes |
|---|---:|---:|
| `medasr_real` | 30 | 0 |
| `medasr_real_paced3` | 90 | 0 |
| `medasr_real_stability5` | 150 | 0 |
| `medasr_snippets` | 60 | 0 |
| `medasr_testdict` | 40 | 0 |
| Total | 370 | 0 |

Comparison used each saved `filtered` string as the formatter input. A separate
layout-only replay through the existing final voice-command pass reproduces
real-headset format 29/30 and numbering 28/30 for both versions. It does not
re-run medical spelling corrections or measure acoustic WER.

The 35-case mixed-command matrix crosses seven native/spoken/literal line
boundaries with five native/spoken numbered item forms. It improved from 23/35
to 35/35. Further iterations added multiline unknown-marker protection, bounded
number tests, and native punctuation followed by unpunctuated spoken layout.

Final focused and adjacent checks: **102 passed** across
`tests/test_medasr_native_format.py` (80) and `tests/test_voice_commands.py` (22).
The session's virtual-environment launcher could not start, so checks used the
already bundled Python with the existing `venv1060/Lib/site-packages` pytest
package added to the import path. Python bytecode and pytest cache writes were
disabled. No packages were installed. Replay imported no `torch`,
`transformers`, MedASR engine, or Whisper engine modules.

## Risks and boundaries for the parent evaluation

Set-off spoken phrases are inherently ambiguous. The adapter deliberately
requires explicit structure and leaves damaged commands and unsupported number
forms for review. Clinical decimals, doses, blood pressures, number words in
ordinary prose, and negation are covered by preservation tests. These are
formatting safeguards, not proof of clinical correctness.

The separate final shared `voice_commands.apply` remains outside this write
set. It has broader existing rules: it can convert line-start `one period of
pain` and punctuation inside an unknown brace marker. The new adapter preserves
those inputs through `render_native` and `postprocess_native`; end-to-end
protection from that later shared pass is not claimed. Any shared-parser change
requires separate ownership and evaluation.

The parent owns recognition/decoder experiments and final paired scoring after
source fingerprints freeze. Missing letters, names, clinical terms, numbers,
negation, and damaged marker tokens remain recognition/decoder problems. A
matched final replay is required before reporting new WER or latency results.

Changed paths: `scripts/medasr_native_format.py`,
`tests/test_medasr_native_format.py`, and this report only.

## Matched decoder calibration review — documentation-only follow-up

Reviewed the parent's local `results_medasr/optimization_20261004/decoder_scores.json`
and `decoder_extra_scores.json`, their corresponding saved raw/cleaned outputs,
and the local manifest. This follow-up changed this report only. Formatter,
tests, production source, and saved result files remain untouched. No inference
or GPU work was performed; no transcript/reference excerpts are reproduced in
this assessment.

The two scorecards have identical corpus and source fingerprints. The selected
decoder, frozen greedy, and frozen Whisper runs also match those fingerprints,
all 30 clip identities, audio hashes, and durations. The recorded formatter hash
still matches the frozen working file. MedASR decoder candidates replay the
same acoustic cache; these are decoder/search comparisons, not new acoustic
model training or evidence that the deterministic formatter recovered damaged
recognition output.

### Aggregate paired results

The selected balance is beam 32, alpha 0.2, beta 0.5. Values below are cleaned,
name-insensitive scores on the same 30 calibration clips.

| Measure | Selected MedASR | Frozen greedy | Frozen Whisper |
|---|---:|---:|---:|
| WER | 8.2% | 11.2% | 6.2% |
| Word errors / reference words | 44/536 | 60/536 | 33/536 |
| Medical WER | 3.1% | 4.1% | 5.1% |
| Medical errors / medical words | 3/98 | 4/98 | 5/98 |
| Target-term hits | 89/94 | 89/94 | 88/94 |
| Format counts | 30/30 | 29/30 | 30/30 |
| Numbering | 29/30 | 28/30 | 30/30 |
| Numeric review flags | 4 | 5 | 1 |
| Negation review flags | 0 | 0 | 1 |

Relative to greedy, total word errors improve on eight clips, worsen on none,
and tie on 22, for 16 fewer errors. Medical error counts improve on one clip and
tie on 29. Relative to Whisper, total errors improve on six clips, worsen on
ten, and tie on 14; the selected decoder has 11 more total errors. Medical error
counts improve on three clips, worsen on one, and tie on 26, for two fewer
medical errors. These comparisons do not establish clinical equivalence.

### Remaining commands and review flags

The decoder resolves the one previously malformed layout marker: its raw output
now contains a valid native command, restoring the missing line boundary and
first numbered item. One damaged number word before a valid native period
marker remains. This accounts for the remaining numbering failure; it should
remain visible rather than be repaired by guessing a list sequence. All
selected outputs meet the scorer's newline/quote-count check, which checks
counts rather than exact layout placement.

The four remaining numeric flags occur on the same four clips already flagged
under greedy. No new flagged clips appear. One examination numeric mismatch
is resolved by the decoder. After removing well-formed line-start list labels,
three selected outputs still differ in their numeric token sequences: two have
age-related errors, and one has examination-number omission/substitution. The
fourth selected flag is explained by the missing list label alone. This is a
supplemental diagnostic using the existing normalizer, not a validated clinical
number parser or a modified scoring rule.

Negation token sequences are unchanged between selected and greedy across all
30 clips, with zero reference mismatch flags for both. Whisper has one such
flag on an examination clip where the selected output has zero scored word
errors. A token-sequence check does not verify negation scope or association
with a particular finding, so zero flags cannot establish preserved meaning.

### Clinically meaningful decoder substitution

The unchanged 89/94 target-term total hides one gain and one loss. The selected
decoder restores an infectious-sampling term that greedy missed, but loses an
autoantibody identifier that greedy and Whisper retained. Alignment locates
the latter as a substitution in raw decoder output, and the loss persists in
cleaned output. The target matcher ignores punctuation, hyphens, and spacing,
so this loss is more than a separator-only difference. It affects a clinical
identifier and warrants review despite the improved aggregate medical WER and
the absence of new numeric or negation flags. The assessment does not infer a
different diagnosis from the unmatched wording.

The no-LM beam-8 control retains that identifier; beam-8 with alpha 0.2 and beta
0.5 loses it. All reviewed beam-32 LM settings and stronger beam-8 LM settings
also lose it. The weakest beam-8 LM setting retains it. This supports an
LM-weight/search tradeoff, including a fixed-beam comparison, rather than a
formatter-induced change. The selected beam-32 comparison does not separately
isolate beam width from LM contribution because a beam-32 no-LM control is not
present in these scorecards.

The weakest beam-8 LM setting also reaches WER 8.2%, with medical WER 2.0%,
90/94 target hits, and three numeric flags, but retains the original 29/30
format and 28/30 numbering counts. Thus the parent's selected balance gains
structure at the cost of a clinical-identifier regression relative to that
alternative. The selected decoder is not uniformly superior on all measures.

### Interpretation and pending work

Nine MedASR configurations were compared on these same calibration clips.
Selection and inspection used this corpus; it is not held out, and the findings
are not a generalization estimate. The lower overall error count demonstrates
a decoder/search improvement on this calibration set. It does not establish
clinical safety, and it must not be credited to the deterministic adapter.

No end-to-end latency conclusion is drawn here. Saved cache-replay processing
times exclude the acoustic forward pass and have no stop-to-text samples. The
parent's actual timing and cross-checks remain pending. Frozen source and test
fingerprints were checked without rerunning or editing their tests.
