# Worker 03: faithful MedASR decoding and clinical accuracy

Write only `results_1060/accuracy_program_20261004/workers/03-medasr-decoder/`.
Read WORKER_COMMON.md. Inspect medasr_engine.py, medasr_ctc_decoder.py,
medasr_decoder_trial.py, medasr_native_format.py and installed official-model
configs/code (without GPU/model loading). Consult official Google model card,
HAI-DEF documentation/research and official decoder/tokenizer references.

Audit our prefix CTC beam/LM implementation against the documented intended
decoder: blank/repeat merging, tokenization, output-mask lengths, pruning,
LM boundary/scoring, alpha/beta semantics and native markup. Separate implementation
defects from model limitations (age placeholders, HGB, rare terms, paragraphs).
Assess why the weak LM repairs the examination while letter age/words remain wrong.
Verify from primary sources whether a larger official MedASR or compatible path
exists; do not invent a larger checkpoint from GPU headroom.

Deliver at most three ranked changes and a bounded comparison with the existing
greedy/weak/balanced controls. A CPU toy CTC test or isolated prototype is welcome
in your folder. State accuracy/latency/dependency implications and how a genuinely
uncached paced run would validate it. No package/model downloads, external decoder
installation, GPU inference, guessed placeholders, broad real-word repair or
production edits. Keep scorer references out of decoder inputs.
