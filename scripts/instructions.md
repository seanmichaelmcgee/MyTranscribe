# Script and trial-harness instructions

Read [root onboarding](../AGENTS.md), [project SOP](../docs/PROJECT_SOP.md) and [readme.md](readme.md) before work here. The assigned script owner controls changes; coordinate imported-helper and adapter edits before touching shared files.

- Preserve default CLI and application behavior. Experimental tracing/replay is explicit opt-in; no hidden installs, downloads, extra model loads/calls, microphone/clipboard access or changed inference settings.
- Keep original PCM identity and explicit warmup/clip/repeat/chunk/builder/decode bindings. Do not discover identity by calling stream factories/builders twice or infer it from call ordinal alone. Preserve raw, filtered and cleaned tracks.
- Metadata observers preserve actual arguments, original results/exceptions and lazy consumption. Restore every experimental patch in `finally`; unknown native stop/attempt fields stay unknown. Routine logs contain timing/count/hash metadata, not patient text or secrets.
- Include every behavior-affecting helper/override/runtime input in source closure. Never alter a script/helper while an active runner fingerprints it. Test CPU transparency/privacy/error/cleanup paths before authorized inference.
- Comparator queues require explicit current spending/data authorization, selected job/model/protocol identity and durable billing state. No unrelated recovery, silent uncertain retry, reference injection or key printing.
- Keep detailed trial outputs local/ignored. Verification and documentation do not themselves authorize inference, API dispatch, commits or a new configuration.
