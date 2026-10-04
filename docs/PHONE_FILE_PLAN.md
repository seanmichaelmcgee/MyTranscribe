# Recording samples on a phone

Use the phone's voice recorder and send its original audio file. M4A and WAV are
fine; phone keyboard dictation only sends text and cannot test recognition here.
Keep these examples fictional, without patient identifiers.

Read from [the sample sheet](samples/personal_v1_read_aloud.md). A useful first set
is **00, 06 and 10**, spoken normally: a short instruction, a neurological exam,
and a referral letter. One file per sample makes review easiest. Label each file
or accompanying message with its sample number and **normal** or **whisper**.
For example: `06 normal`. After that, repeat the same three while whispering,
keeping the phone position constant. We can also use combined recordings; give
the sample numbers in order and mention any wording changes or omitted commands.

Send the original file in this chat. I will confirm that the actual audio file is
accessible before claiming it has reached the local machine. If the attachment
is unavailable locally, we will need an original-file transfer through your
existing remote connection. No new remote service is required by this importer.

Samples **09, 12 and 13** remain reserved for validation after choosing settings
on the other samples. We will confirm what was intended before scoring, including
any changed wording, without using an engine's transcript as the answer key.
Personal names are excluded from name scoring; medical terms such as Romberg
remain included.

## What happens locally

The importer retains a byte-identical original and converts a copy to 16 kHz mono
PCM WAV. It applies no added gain, noise reduction or trimming. Both engines will
receive that same converted waveform. Imports, audio, references and diagnostics
stay in ignored local results folders, outside Git.

Phone files have their own capture condition, separate from local-headset and
remote-microphone recordings. Normal and whispered files use separate default
folders. Recognition timings exclude upload and transfer time; replaying a saved
file does not measure the complete phone recording workflow or live Stop delay.
Phone microphone processing can affect the result, so it is not evidence that
the local microphone will perform identically.

Once a real file and its intended wording are available, compare the current
Whisper baseline and existing MedASR settings sequentially and offline. Retain
source, model, configuration and corpus fingerprints. Review medical vocabulary,
ordinary words, formatting, numbers and negation alongside processing time.

## Local operator instructions

From the MyTranscribe folder, after transferring the original file locally:

```powershell
.\venv1060\Scripts\python.exe .\scripts\import_phone_samples.py --input 'C:\path\sample06.m4a' --samples 6 --voice normal
```

For a combined recording, use the actual order, such as `--samples 0,3,6,7`.
For whispered speech use `--voice whisper`. Default destinations are
`results_1060/phone_files_v1_normal` and `results_1060/phone_files_v1_whisper`.
An explicit `--out` must remain inside a gitignored local results directory.
Each repeat gets a distinct original, WAV and manifest entry. Every imported
reference is marked as requiring review before scoring.

The importer uses the already installed PyAV on CPU. It accepts one audio track
and no video, with a 100 MiB file limit, ten-minute decoded duration limit and a
90-second timeout on its own decoding child. It rejects unsupported containers
and denies secondary media opens. FFmpeg documents its
[container allowlist](https://www.ffmpeg.org/ffmpeg-formats.html) and
[protocol allowlist](https://ffmpeg.org/ffmpeg-protocols.html); the importer sets
both explicitly rather than leaving their defaults unrestricted. These limits
reduce the decoding scope; the child process is not a separate security sandbox.
No model, package, microphone listener or remote service is added.

## Verification and current status

Checks cover exact PCM retention, a real 48 kHz AAC/M4A conversion, rejection of
an external-reference playlist, the duration limit, unpublished failed imports,
preservation of originals and repeated samples, and combined held-out references.
The actual child-process import also passed with a generated one-second WAV.
That fixture is labeled synthetic and is not part of the personal sample corpus.

The final full-suite run had **450 passed and one failed** in 32.80 seconds.
The existing Windows clipboard round-trip check also failed on focused reruns;
all seven importer tests passed. A separate synthetic diagnostic confirmed that
Windows refused `OpenClipboard`, and neither plain nor privacy-marked Qt copies
changed its sequence number or could be read back. This session cannot validate
clipboard integration until access returns. No clipboard or production app code
was changed, and the failing test was not skipped or weakened.

No phone recording has arrived yet. This work prepares ingestion; it supplies no
new recognition accuracy score. The earlier ordinary-app recording was not saved
as replay audio and has not been recovered by this importer.
