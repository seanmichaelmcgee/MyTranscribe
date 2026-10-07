# Isolated MedASR trial on this Windows machine

The working Whisper GUI keeps its current runtime and defaults. MedASR is an
experimental replay adapter, not a selectable clinical app engine yet. The trial
reads only existing fictional practice recordings; it never opens a microphone,
clipboard, web inference endpoint, or model repository code.

## Setup and access

From the MyTranscribe folder in PowerShell:

```powershell
.\scripts\setup_medasr.ps1
```

Creates gitignored `venvmedasr`, installs official PyTorch 2.13.0 CUDA 12.6 wheels
and pinned Transformers 5.18.0; transitive versions are frozen in
`requirements-medasr.lock.txt`. It reuses the existing trusted CA bundle when
present. It uses Windows extended paths for the installer to avoid PyTorch's
nested license files exceeding MAX_PATH; it does not change registry settings.
Do not install these packages into `venv1060`. No torchvision, audio codecs,
external language-model decoder, or third-party model conversion is needed.

Review [Google's model access page](https://huggingface.co/google/medasr) and
[Health AI Developer Foundations terms](https://developers.google.com/health-ai-developer-foundations/terms).
Accept access conditions through your own account. Login locally with the browser/device-code option (browser sign-in alone does not
authorize local downloads; do not paste secrets into an agent chat):

```powershell
$env:SSL_CERT_FILE = (Resolve-Path venv1060\ssl\ca-bundle.pem).Path
$env:REQUESTS_CA_BUNDLE = $env:SSL_CERT_FILE
.\venvmedasr\Scripts\hf.exe auth login
.\venvmedasr\Scripts\python.exe scripts\download_medasr.py --ca-bundle venv1060\ssl\ca-bundle.pem
```

The downloader uses only `google/medasr` revision
`ae1e4845b4b07479735d93e1e591e566435b7104`, allowlisted tokenizer/config files
and `model.safetensors`. It verifies the weights against upstream LFS SHA256 and
records all file hashes locally. It never downloads Python, pickle, notebooks,
test audio, or external 6-gram language-model files. Inference verifies the hashes
again, sets offline mode and disables remote code and pickle weights. Local hashes
provide provenance/corruption checks, not a signed guarantee of model safety.

An optional offline installation check uses tiny random weights, without accessing
the gated pretrained model:

```powershell
.\venvmedasr\Scripts\python.exe scripts\smoke_medasr.py
```

This validates preprocessing and GPU CTC generation/decoding; it provides no evidence
about MedASR accuracy or performance.

## Paired replay and scoring

Run only one GPU replay at a time. These commands use the same 16 kHz mono int16
practice audio and the same frozen 20 s pause-cut comparison pipeline, silence
threshold, per-chunk phantom filter, spelling correction, bundled text fixes and
final voice-command formatter. Personal correction files and environment overrides
are excluded so the comparison can be reproduced. Whisper uses large-v3,
int8_float32, beam 5, patience 2, with its current topic/recent-text prompts.
MedASR uses greedy CTC with no prompt or external language model.

The production Whisper application now uses 30-second chunks. The commands below
retain the original 20-second comparison baseline; use `trial_chunk_window.py
--chunk-seconds 30` for the current window. See the
[current comparison](overnight/2026-10-04-asr-optimization.md) and
[optional official-LM decoder experiment](MEDASR_DECODER_EXPERIMENT.md) for the
later controlled trials. Do not mix their cached-decoder timings with live latency.

```powershell
.\venv1060\Scripts\python.exe scripts\trial_asr.py --engine whisper --manifest results_1060\real_headset\manifest.json --out results_medasr\whisper_real.json
.\venvmedasr\Scripts\python.exe scripts\trial_asr.py --engine medasr --manifest results_1060\real_headset\manifest.json --out results_medasr\medasr_real.json
.\venv1060\Scripts\python.exe scripts\score_asr_trial.py --manifest results_1060\real_headset\manifest.json --run results_medasr\whisper_real.json --run results_medasr\medasr_real.json --out results_medasr\paired_real_scores.json
```

For warm Stop-to-final-formatted-text measurements use `--realtime --repeats 3`
and separate output filenames for each engine. `--only message,result` selects
short snippets; pass the same filter to the scorer. Include `exam,letter` for the
longer workflow. The recorded wait includes final formatting and worker draining,
but excludes GUI polling and clipboard transfer. Fast replay records processing
seconds and compute/audio ratio, not live Stop latency. Startup and warmup are
reported separately. Missing latency is null, never a misleading zero.

The primary trial deliberately uses the app's non-overlapping pause cuts. Google's
published example also supports sliding windows of 20 s with 2 s overlap; that is
a different inference configuration and must be a separately labeled experiment
before adopting it. Float32 is the initial GPU trial; `--precision float16` is an
optional paired rerun. CPU must be selected explicitly; GPU fallback cannot quietly
produce mislabeled CUDA results.

The observed float16 configuration on this GTX 1660 Ti produces nonfinite logits
and blank text; retain float32. The adapter now validates generated logits and
raises an explicit error rather than accepting NaN/Inf argmax output as a decode.

An optional downstream formatting experiment uses `--medasr-format native-v1`.
It interprets only the five exact initial markers: `{newline}`, `{new paragraph}`,
`{open quote}`, `{close quote}` and `{period}`. Explicit number-plus-period commands
at a native line boundary become numbered items. Unknown markers are preserved
and protected from spelling guesses. Raw output remains unchanged in the record.
This policy is opt-in, applies only to the isolated MedASR replay, and has its own
source fingerprint. It does not infer layout where the model omitted a command.

[Google's discussion of brace tokens](https://discuss.ai.google.dev/t/116107/4)
describes them as explicitly spoken commands and documents varied training forms.
Our five-marker policy is an application choice, not a complete or guaranteed
supported-command list.

## Bounded overnight runner

The [overnight plan](overnight/2026-10-03-medasr-overnight-plan.md) defines the
finite accuracy, precision, paced-latency, synthetic and stability matrix. Review
its commands without loading a model or starting GPU work:

```powershell
.\venv1060\Scripts\python.exe scripts\overnight_medasr.py --dry-run
```

After downloading and verifying the official snapshot, start a fresh local run:

```powershell
.\venv1060\Scripts\python.exe scripts\overnight_medasr.py --hours 6 --out results_medasr\overnight_20261003
```

The runner writes `status.json`, task logs and JSON scorecards in that ignored
directory. It blocks before GPU work if model integrity is unavailable, serializes
jobs with an OS-held lock, enforces subprocess and overall deadlines, and samples
GPU health. It finishes early when its matrix is complete. A resume must use the
same configuration and preserves the original deadline:

```powershell
.\venv1060\Scripts\python.exe scripts\overnight_medasr.py --hours 6 --resume results_medasr\overnight_20261003
```

Successful outputs are reused only after source, corpus, model, configuration and
artifact checks. Changed source or stale artifacts require a fresh run directory;
do not delete the prior measurements. For tonight, no fresh run may extend beyond
03:45 Halifax on 4 October. Use a shorter `--hours` budget if starting late.
Keep the computer and Codex app running for the scheduled checks in this chat.

After preserving the initial matrix, a separate fresh-source float32 matrix can
test the formatter with paired Whisper, paced delay, synthetic and stability runs.
It excludes the already-failed float16 experiment:

```powershell
.\venv1060\Scripts\python.exe scripts\overnight_medasr.py --native-format --hours 5.3 --out results_medasr\overnight_native_20261003
```

The 5.3-hour budget above applies to this night's approximately 22:20 start; shorten
it for a later start to respect the 03:45 Halifax cutoff. Never resume the old
unadapted matrix after source changes; its completed results remain archived.

For synthetic cross-checks substitute `results_1060\snippets\manifest.json` or
`results_1060\testdict\manifest.json`. Report each separately: synthetic snippets
reuse the real test texts, and the longer dictations repeat texts across microphone
profiles. These are not 130 independent examples.

## What the scores establish

Audio SHA256 plus manifest contents freeze the corpus, including reference text,
names and key terms. Pipeline/scorer source hashes and package versions are saved.
The scorer rejects changed datasets/source, missing clips, duplicates and unfinished
runs. Raw and cleaned text come from the same decoding run: raw is compared to the
spoken reference (including commands), cleaned to the written reference. Both
engines use the existing name exemptions, including the three letter scenarios.

Historical WER, medical-word error, common-word error, rare unmatched words/100,
term recall and newline/quote-count checks use `src/eval_metrics.py`. Counts and
denominators are included. Medical/common error excludes insertions; rare unmatched
words are a frequency heuristic, not a verified hallucination count. Term recall
uses substring matching. Formatting counts do not establish correct placement;
numbered-item sequences are checked separately. Numeric/negation token differences
are additional review flags, not semantic safety scores. Raw term recall retains
historical number normalization limitations.

Inspect errors in doses, units, negation and layout locally before choosing an
engine. CTC can produce incorrect or extra words; it does not guarantee absence of
hallucination. Google's benchmark table is not a prediction for this clinician's
voice, microphone or app pipeline. Three recorded letters give preliminary evidence
only. Transcripts and full JSON stay in ignored result folders; commit only scripts,
aggregate measurements and findings. Do not copy practice audio into reports.

## Primary references

- [Official MedASR model card](https://huggingface.co/google/medasr)
- [Official LASR/Transformers documentation](https://huggingface.co/docs/transformers/model_doc/lasr)
- [Google MedASR repository](https://github.com/Google-Health/medasr)
- [Official CUDA 12.6 wheel instructions](https://pytorch.org/get-started/previous-versions/)
