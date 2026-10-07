# Worker 04: quiet speech, capture and microphone quality

Write only `results_1060/accuracy_program_20261004/workers/04-audio-capture/`.
Read WORKER_COMMON.md. Inspect mic_ready.py, chunked_transcriber.py, input meter,
fw_engine VAD, importer conversion and existing level/VAD artifacts. CPU-only
signal analysis of the explicitly supplied fictional phone/headset waveforms is
allowed; no microphone recording and no inference.

Separate actual whispered phonation from reduced amplitude and phone processing.
Audit capture onset/pre-roll, gain level, resampling, clipping/noise, quiet-frame
cuts, RMS gating and VAD. On 011 VAD bypass does not change section recognition,
so do not present VAD lowering or indiscriminate gain as a proven fix. Peaks near
full scale constrain uniform boosting even though average level is quieter.

Deliver a minimal paired mic/normal/whisper protocol and at most two justified
bounded input-processing experiments, with precise diagnostics, post-processing
meter semantics and rejection criteria. Cover headset, conference/tenor-like mic
and PowerMic as separate capture conditions. Identify what phone files cannot
establish about the local workflow. Prefer an inspectable CPU signal prototype
with gain/limiter/noise effects specified over adding opaque dependencies. State
which missing device facts or new fictional recordings would settle the question.
