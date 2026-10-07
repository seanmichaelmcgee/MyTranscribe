# Isolated MedASR decoder experiment

The working application still uses Whisper. This experiment uses the same pinned
official MedASR weights, float32 CUDA and app chunking, with optional prefix beam
search and Google's official six-gram SentencePiece language model. It adds no
packages to either environment and does not load executable model code.

Google's [official example](https://github.com/Google-Health/medasr/blob/main/notebooks/quick_start_with_hugging_face.ipynb)
uses pyctcdecode and KenLM. This trial instead implements a small NumPy prefix
beam search and reads a SQLite index of the official ARPA probabilities. It is
**not an exact reproduction of Google's decoder**. Beam width, token pruning,
language-model weight and token insertion bonus are explicit trial settings.
The model architecture and acoustic weights do not change.

## Prepare official probability data

From the repository root, using the existing authenticated local environment:

```powershell
.\venvmedasr\Scripts\python.exe scripts\prepare_medasr_lm.py --ca-bundle venv1060\ssl\ca-bundle.pem
```

The only downloaded file is `lm_6.arpa.xz` at official revision
`ae1e4845b4b07479735d93e1e591e566435b7104`, 240,317,220 bytes, SHA256
`bf0119b19ba8811fb91b67c7374fa02baa6a0f0660d1235f2192f4d6874c2b3b`.
The parser checks finite probabilities, declared/actual row counts, order up to
six, line size and a four-GiB uncompressed limit. It indexes 33,531,288 ngrams into
1,353,625,600 bytes of local SQLite data. Preparation takes several minutes.
Files remain under ignored `models_medasr/language_model/<revision>/`.

The index is reopened read-only with extensions disabled by default. Its checksum
and official archive provenance are verified before decoding. SQLite provides
data lookups; no downloaded scripts, pickle objects or third-party decoder DLLs
are executed. No microphone, clipboard or network is used by inference.

## Compare decoder settings

First collect a fresh acoustic cache with greedy decoding:

```powershell
.\venvmedasr\Scripts\python.exe scripts\medasr_decoder_trial.py --manifest results_1060\real_headset\manifest.json --medasr-format native-v1 --out results_medasr\my_decoder_trial\greedy.json
```

Then use the identical verified logits for a CPU decoder comparison:

```powershell
.\venvmedasr\Scripts\python.exe scripts\medasr_decoder_trial.py --cache-only --beam 32 --alpha 0.2 --beta 0.5 --lm models_medasr\language_model\ae1e4845b4b07479735d93e1e591e566435b7104\ngrams.sqlite --manifest results_1060\real_headset\manifest.json --medasr-format native-v1 --out results_medasr\my_decoder_trial\beam32_lm.json
.\venv1060\Scripts\python.exe scripts\score_asr_trial.py --manifest results_1060\real_headset\manifest.json --run results_medasr\my_decoder_trial\greedy.json --run results_medasr\my_decoder_trial\beam32_lm.json --out results_medasr\my_decoder_trial\scores.json
```

Use a new output directory for each source freeze. Cached waveforms are keyed by
waveform content, official model fingerprints, float32 precision, runtime versions
and adapter/cache source. Array hashes are checked; NumPy loads have pickle
disabled. References are used only by the scorer, never recognition or decoding.
The trial scorer rejects stale source/corpus fingerprints and incomplete runs.

`--beam 0` is greedy; a positive beam without `--lm` tests acoustic prefix search.
Default token limit is 16 per frame, with a log-probability threshold of -8 and
blank always included. Alpha weights the LM natural-log score; beta rewards each
new SentencePiece token, not each clinical word. Larger weights can worsen output.

## Timing and interpretation

`--cache-only` measures decoder/pipeline work and cannot measure clinical
Stop-to-text latency. For a paced acoustic trial, use `--realtime` and a **fresh,
empty `--cache` directory** so every waveform is inferred on the GPU. These trial
measurements include local cache writes and exclude GUI/clipboard overhead.
Do not run another GPU job at the same time. Score latency and clinical review
signals before considering integration into the application.

The existing 30 recordings are a calibration set, not an independent held-out
accuracy test. Synthetic microphone/profile repeats are correlated. Formatting
counts, numbered sequences and number/negation token flags require review and
cannot establish clinical correctness. Do not infer broad medical superiority
from differences of one or two missed medical words.

Measured iteration results are in
[the optimization report](overnight/2026-10-04-asr-optimization.md).
