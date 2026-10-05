# Opt-in original-audio trials

`scripts/personal_audio_trial.py` replays frozen local capture manifests through the existing trial adapters. It supports multiple original WAVs without the historical replay's int16 rescaling. The input must be 16-kHz mono PCM16, and the recorded output includes original audio and PCM hashes, adapter identity, and corpus/reference identity. It never opens the microphone or calls a remote service.

Use the installed trial environment and run `--help` for the wrapper options. Supply one or more `--manifest` paths and a new `--out` path inside an ignored `results_*` folder. Choose `--backend whisper` or `--backend medasr`, with an explicit `--chunk-seconds 20` or `30`. Remaining model and decoder arguments are forwarded to the corresponding runtime/decoder adapter. Use the installed local model and keep GPU jobs sequential under the existing runner lock. An external controller must enforce the overall deadline and owned-child timeout.

A Whisper vocabulary experiment requires both `--candidate-vocabulary` and `--candidate-topics`. The wrapper changes the prompt builder while retaining the baseline correction pipeline. It records the vocabulary hash and refuses changed inputs or incomplete coverage. MedASR rejects vocabulary-prompt candidates because its acoustic adapter does not use Whisper prompts. Each invocation performs one offline pass over the explicit manifest scope.

For MedASR, fresh greedy acoustic collection and language-model decoding can share a verified cache at the same chunk target. Cache-only results measure decoder/pipeline work; they must not be presented as microphone-to-text latency. Paired comparisons must preserve model, runtime, source, original PCM, chunking and cache fingerprints.

The capture helper supports readable packet labels and an intended clear/fast delivery hint. Actual speech, delivery and skipped words still require separate confirmation; metadata cannot establish them. Preserve every take and select replacement takes before comparing model scores.

Compare medical identities and assertions, including extra medications, doses, decimals, units, frequency, negation, laterality and separate-case paragraph boundaries. Word-error rate and expected-term presence alone cannot detect every clinically significant change. Valid medical words may still be incorrect substitutions. Keep intended scripts, confirmed speech, uncertain spans and model hypotheses distinct, and preserve metric versions. A vocabulary improvement must not gain acceptance by deleting clinical content or overlooking a new negation or formatting regression. Ordinary application defaults remain unchanged by these opt-in tools.

Selected remote queue jobs recover only their own provider/protocol scope. Completed responses are reusable; unrelated in-flight jobs are not altered, and uncertain paid outcomes are not resubmitted automatically.
