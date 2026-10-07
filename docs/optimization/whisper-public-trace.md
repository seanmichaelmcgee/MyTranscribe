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

## Optional native attempts

`--trace-native-attempts` requires `--trace-decoder` and is also off by default.
The trial owns instance wrappers for `get_prompt`, `generate_with_fallback`,
and an attribute-delegating native-model facade intercepting only `generate`.
Original arguments, result lists, fallback tuples and yielded segment objects
remain unchanged. No fallback loop is copied. Concurrent owners of the same
model are rejected. Every installed binding, including the outer adapter's
`transcribe`, is restored when the owner closes. The final successful checkpoint
closes owners before publishing metadata; cleanup failures mark the native
trace incomplete and do not replace recognition exceptions.

The separate `native_decoder_trace` records ordinal public-call, prompt,
fallback-window and native-attempt identities; exact native/previous-token and
generated-sequence count/hash; actual numeric/boolean generation kwargs;
suppressed-token count/hash; and exposed numeric scores/no-speech probability.
Positive temperature comes from actual `sampling_temperature`; the zero branch
is labelled from the inspected beam/patience path. Selected native-result
identity is matched only within its fallback call, independently of reported
final temperature. An absent or ambiguous result identity remains unknown and
makes the trace incomplete. Object IDs, token IDs and decoded token text are
never stored. Inspected Python implementation source hashes are retained.

Bounds are 256 fallback windows, 512 prompt events, 1536 native attempts,
16 results/sequences/scores per attempt and 4096 tokens per hash. Original
iterators are never consumed to obtain metadata. Limits, metadata failures,
missing public/prompt/window bindings and failed restoration prevent native
`complete=true`; in the saved result it also requires public-layer completion.
Completeness applies only to these observed native windows. The public-layer
`unobserved` list still describes that layer's scope; the separate native section
supplies its additional observations. Native generation can precede discarded
or un-emitted tokens; generated totals remain distinct from emitted totals.

Fallback rejection causes, internal reset events and native stopping reasons
remain unknown/null. No stop reason is exposed in the inspected installed
result path; token length does not establish truncation. Whole-audio/clip/
repeat/chunk, skipped-chunk and warmup bindings, VAD-to-original-audio mapping,
builder calls, context rotation and recording resets are deferred. Neither
layer certifies causal attribution or clinical fidelity. The tests use CPU
fakes only; no new model inference accompanies this implementation.
