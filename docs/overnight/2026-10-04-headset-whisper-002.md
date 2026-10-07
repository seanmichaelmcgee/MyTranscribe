# Whispered headset and personal curriculum — 4 October 2026

The user completed the requested whispered reading. A second, explicitly labeled
`local_whisper` WAV saved without a capture error: 44.608 seconds, 16 kHz mono PCM.
Its RMS is −43.78 dBFS, about 9.23 dB below the paired normal reading; peak is
0.105 full scale with no clipping. Phonation is supported by the requested reading,
the selected capture label and user completion; no direct listening is claimed.
Scores compare with the frozen intended script and retain that provenance.

The three unchanged controls were frozen and replayed on original PCM, with the
same model/settings and explicit 30-second Whisper / 20-second MedASR chunk routes
as the first headset iteration. Whisper again reproduces the live formatted
transcript exactly. No phone file or extra microphone was added to this phase.

| Whispered control | Historical cleaned errors | BP-notation-normalized errors | Terms | Offline warm compute |
|---|---:|---:|---:|---:|
| Current Whisper | 14/113 (12.4%) | 14/113 (12.4%) | 13/17 | 6.160 s |
| MedASR greedy | 10/113 (8.8%) | 7/113 (6.2%) | 16/17 | 0.212 s |
| MedASR weaker LM | 9/113 (8.0%) | 6/113 (5.3%) | 16/17 | 0.394 s |

Whisper writes HGP for HGB, a malformed examination term, and loses the negative
nystagmus assertion. Its medication name is wrong and it inserts an extra b.i.d.
frequency before the spoken daily. Age 72, BP 132/78 and exertional discomfort
remain correct. MedASR preserves the negative examination statement and medication
tuple, but both controls give HTP for HGB and retain a bracketed medication header
and ordinary-word errors. Neither is promoted; aggregate improvement does not
overcome a clinical substitution or inserted instruction.

The fixed new phase window was 22:20:48–22:35:48 UTC; all three controls finished
at 22:21:59 UTC. Each child had a 300-second limit, under the existing exclusive
GPU lock and thermal guard. Peak sampled card use was 3,927 MiB at 47 C. All
children exited. These are single offline compute observations, not Stop-to-text
latency or a clinical reliability estimate.

## Accepted spelling and ongoing adaptation

The user expressly accepts both `dysdiadokinesia` and `dysdiadochokinesia`. A new
opt-in evaluation policy credits those complete-token spellings symmetrically,
while preserving all original literal scores, references and transcripts. It
does not equate the observed `dysdiatokinesia` or `dysthytokinesia` with them.
Accepted-spelling evaluation leaves these cleaned headset totals unchanged;
it credits the valid variant in some raw MedASR outputs. It never changes a dose,
drug identity, negation or formatting in the saved output.

The [personal curriculum](../PERSONAL_ASR_CURRICULUM.md) now supplies persistent
human feedback, versioned term/style policy, compatible candidate vocabulary
exports, literal/accepted-spelling scoring and a first fictional lesson with
separate calibration and validation packets. Personal medication priorities
and spelling proposals stay in ignored local data. Twenty names from the user's
list are recorded as explicit priorities; five proposed canonical identities
await clarification. The user requested ordinary medical terms as well as
specialist/oncology vocabulary. Exact oncology regimen names require confirmation.
Detailed style preferences are still unspecified.

The ongoing curriculum focuses on the user's everyday headset and normal/whisper
readings. Phone samples remain optional historical evidence and are excluded
from new curriculum selection. A second microphone can be tested when it becomes
part of the intended workflow. No scheduler, automatic app vocabulary activation,
remote upload or model-weight update was added.

The full suite passes **478 tests in 33.53 seconds**, including accepted-spelling
boundaries, preserved clinical fields, conflicting/numeric-rule rejection,
persistent feedback, immutable candidate versions and literal-versus-equivalent
scoring with unchanged inputs. The production GUI/prompt/decoder settings stay
unchanged; the new functionality is opt-in curriculum tooling.

## Recovery

Both headset WAVs, live diagnostics, immutable whisper corpus, plans, detailed
reviews and telemetry stay under ignored
`results_1060/headset_iteration_20261004`. Whispered WAV SHA-256:
`31bc6ae393249c5c0aef42e0001501508426d2d4dbc610f2a0e933d9ab428e9c`.
The first phase's one-entry manifest was reconstructed byte-for-byte and verified
against its frozen hash after the capture manifest appended this repeat. Its
`manifest_snapshot.json` / `manifest_resolution.json` preserve historical identity;
the old plan, outputs and scores remain unchanged.

The persistent curriculum root is `results_1060/personal_curriculum`. Read
`status.json`, `curriculum.json`, `feedback.jsonl` and `policies/v1.json`; the
paired accepted-spelling scorecard is `scores/headset_pair_policy_v1.json`.
The first lesson and reserved validation text are under `lessons/01`. Candidate
vocabulary is under `candidates` and remains inactive pending paired trials.
