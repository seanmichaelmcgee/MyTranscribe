# Product requirements and proposed decision gates

## User requirements

Three workflows: very brief HGB/eGFR results and booking/message instructions;
complex clinical/exam fragments with abbreviations, uncommon medical words,
numbers and negation; and 30–60-second paragraph referrals with medications,
values, numbered items when dictated, and clinician style.

Medical fidelity and low correction effort matter more than names or a headline
word score. Quiet or whispered near-mic speech is a desired future capability.
The user described an approximately-three-second short-task workflow and regards
an extra two-second wait after a ten-second dictation as too slow. A similar wait
on a 30–60-second letter can be acceptable if accuracy improves.

Clipboard output is acceptable. Preserve compact startup, smoothly expandable
debugging, F9 hold-to-talk, mouse-forward toggle, a clear green recording/red idle
indicator, options showing bindings/hold versus toggle, and a volume meter that
represents the actual model input including any future applied gain. Stable,
clean Windows-style UI takes priority over adding more controls. A short/long mode
needs a measured advantage before increasing daily interaction cost.

Inference stays local/offline. Keep clinical capture in memory in the ordinary
app, and fictional-test saves explicitly separate and ignored. Prefer a small
inspectable dependency surface. No cloud reviewer, new package, executable model
code, service, hosted GPU rental or remote-machine transfer to force an outcome.
The 4070 Ti Super 16 GB and rental GPUs are future benchmark options, not current
authorization to spend money or move audio. Security is a design/evidence claim,
not a guarantee implied by small code or passing tests.

## Proposed engineering gates (reviewable targets, not promises)

| Dimension | Initial target / decision rule |
|---|---|
| Critical clinical content | No new silent number/unit/medication/negation errors in matched controls; explicitly inspect age, BP, HGB/eGFR and changed/unchanged findings. Correct 72/132/138 must not be inferred from a prompt or expected script. |
| Short-result copying | Candidate must prevent copying unrelated example names/values on both phone short crops; also preserve ordinary results in the older corpus. Returning a visibly flagged uncertain result can be safer, but is not an accuracy success. |
| Medical/common accuracy | Evaluate per workflow and raw versus cleaned. Do not promote a medical gain that hides a common-word or clinical-field loss in aggregate WER. Keep exact denominators and reference provenance. |
| Short finishing delay | Aspirational warm local median <=0.5 s and p95 <=1.0 s for <=10-second clips. The user has not accepted these precise thresholds; state measured distance from them. Approximately 2 s for a brief instruction is outside the desired workflow. |
| Longer finishing delay | Aspirational warm local median <=2 s for 30–60-second dictations when content improves. Include full-file speech-end/tail effects and no distribution claims from one sample. |
| Interactive workflow | Measure start readiness and actual copy/paste separately from inference. File replay/headless Qt do not validate microphone routing or Windows clipboard access. |
| Formatting | Preserve newlines/paragraphs/quotes/numbered intent without rewriting prose or turning unknown native tokens into invented clinical text. Count checks alone do not establish semantic formatting. |
| Validation | The older 30 clips and both phone files are calibration. Require a frozen unseen set, including genuinely whispered and microphone-specific audio, before calling a change general or clinically validated. 09/12/13 stay reserved. |
| Promotion | Baseline/candidate must match source/model/runtime/audio/reference identities; relevant tests must pass. Revert a candidate with new critical errors, unsafe corrections, unacceptable latency or unsupported dependencies. |

The supplied Frontier transcripts provide another comparison track. Score literal
written agreement separately from clinically equivalent notation (e.g. 138/78
versus 138 over 78). Define equivalences before inspecting candidate differences.
Do not assume formatting commands were absent because the external transcript
omits them. Do not report raw/spoken WER against that formatted text as though it
were a verbatim spoken transcript. Critical insertions must be counted/reviewed;
the historical medical/common metric does not count all insertions.

## Optional reviewer specification

The coordinator should scope feasibility of deterministic rules, broad medical
hints and a local LLM reviewer. Keep them separate from acoustic improvements.
A reviewer must preserve clinically material values/negation, expose uncertain
changes, avoid fabricating a diagnosis and have measured latency/memory/offline
requirements. Transcript-only reviewers cannot recover an unheard number with
certainty. No new reviewer weights or dependencies are approved by this program;
specify a later opt-in trial if needed. Include anti-feedback measures so a
reviewer's guesses do not silently become the next chunk's acoustic prompt.
