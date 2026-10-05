# Experimental Whisper public-call trace

`scripts/whisper_runtime_trial.py --trace-decoder` adds a bounded, versioned
`decoder_trace` section to the chosen ignored result. The option is off by
default; the earlier minimal `decoder_traces` diagnostics remain. No production
engine, prompt builder, inference argument, fallback policy or token budget is
changed. The helper is included in the adapter's source fingerprints.

The trace hashes the actual float PCM passed before VAD, retaining its dtype,
frame count and known 16-kHz sample rate. It records the actual passed initial
prompt hash/character count, passed output-token cap, configured temperature
schedule and numeric/boolean options. Returned info is whitelisted to numeric
and boolean fields, including original and post-VAD durations. Each segment is
observed only as the original iterator yields it: emitted-token count/hash,
reported temperature and the available numeric diagnostics are retained.
Original segment and info objects, call counts, kwargs, lazy consumption and
recognition exceptions are preserved. The existing tracked-loop behavior for
`send`, `throw` and `close` is retained; this layer adds no iterator forwarding.

Prompt text is omitted unless `--trace-prompt-text` is also explicitly supplied.
That flag requires `--trace-decoder` and saves text only in the same private
ignored result. No prompt, token IDs or exception message is printed. Token
IDs are never retained or decoded for telemetry. Hashes provide linkage and
do not anonymize text. Trace-on legacy parameter metadata is also whitelisted
to prevent caller prefix/hotword values from leaking.

The run retains at most 256 calls and 4096 segments. Token hashing is bounded
to 4096 existing integer tokens per segment; explicit prompt text is bounded
to 8192 characters per call. Overflow or metadata capture failure sets trace
`complete=false` without truncating recognition or changing its exceptions.
Failures record stage and exception class only. A partial/closed iterator
cannot be reported as an exhausted complete trace. Closing before first
iteration is not explicitly observable by the existing generator wrapper;
the trace remains incomplete.

`complete` means only this public metadata layer completed within its limits.
Native generation attempts, selected fallback-result identity, native prompt
tokens, fallback rejection decisions, VAD window mapping, warmup/clip/repeat/
chunk binding, builder context, topic rotation and reset events remain
unobserved. A segment's reported temperature does not identify the attempt
that supplied its text. Emitted-segment token totals are not native generation
totals. Stop/finish reasons remain null: output length or an EOS-looking token
does not prove cap truncation. This first layer cannot establish the cause of
a missing dose or paragraph, adjudicate actual speech, or certify clinical
fidelity. A future already-declared frozen trial may enable it; no new model
inference was used to implement or test it.
