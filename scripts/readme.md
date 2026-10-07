# Scripts how-to

Follow [instructions.md](instructions.md) and [project SOP](../docs/PROJECT_SOP.md). These scripts include application helpers and experimental harnesses; a command example explains use, not permission to launch a job. Run from the repository root with the established environment.

## Choose the right entry point

| Script | Use |
|---|---|
| `personal_curriculum.py` | Maintain the local curriculum/policy and evaluate saved results; [curriculum guide](../docs/PERSONAL_ASR_CURRICULUM.md) |
| `personal_audio_trial.py` | Opt-in verified original-PCM replay and isolated prompt candidates |
| `trial_asr.py` | Shared offline raw/filtered/cleaned replay harness; historical PCM route differs from exact replay |
| `whisper_runtime_trial.py` | Fixed local Whisper runtime trial and opt-in trace adapter |
| `whisper_decoder_trace.py`, `whisper_native_trace.py` | Experimental observation helpers; [trace interface](../docs/optimization/whisper-public-trace.md) |
| `frontier_audio_queue.py`, `openrouter_audio_queue.py` | Authorized blind remote comparisons with durable selected-job state |

For commands/options and provenance rules, use the linked guides and the script's `--help`. Inspect the current scoped plan before choosing a manifest, candidate, model or output. A fresh ignored output path preserves prior evidence. Personal headset capture/replay details are in [personal-audio-trials.md](../docs/personal-audio-trials.md); external reference policy is in [PERSONAL_ASR_CURRICULUM.md](../docs/PERSONAL_ASR_CURRICULUM.md).

## Development and checks

1. Read the assignment and relevant source/test files; confirm ownership and active-run fingerprints.
2. Make the smallest isolated change. Keep ordinary defaults and baseline correction behavior intact. Register new helpers in the provenance closure.
3. Run the relevant CPU checks. For the existing Whisper trace/exact-replay area, a focused starting set is:

```powershell
.\venv1060\Scripts\python.exe -m pytest -q tests/test_whisper_runtime_trial.py tests/test_whisper_native_trace.py tests/test_personal_audio_trial.py
```

Use the tests appropriate to the final changed interface; expand only for a new concern. The MedASR environment and tests are separate. No GPU recognition or API request is necessary for observer/fake-interface checks.

4. Report changed behavior, actual checks, artifact paths and remaining limits to the coordinator. Freeze a new experimental source/config identity only after integration and review; existing active runs remain immutable.

## Progress overview

Experimental trace interfaces and exact replay are documented separately from production engines. A trace can complete without exposing a finish reason, adjudicating speech or proving clinical safety. Read the current local checkpoint and scoped plan for native/binding integration and replay status; this readme is not an experiment log.
