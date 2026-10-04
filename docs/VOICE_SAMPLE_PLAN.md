# Next personal voice and microphone comparison

The current results favor Whisper and suggest 30-second cuts improve longer
letters. Short recordings flush when stopped, regardless of that maximum cut
window. Test new independent examples before treating a calibration gain as a
general accuracy guarantee. Keep one simple recording workflow initially.

The [first personal read-aloud packet](samples/personal_v1_read_aloud.md) is ready:
14 new fictional examples with frozen written references, three reserved validation
samples and separate normal/whisper capture commands. The recorder accepts its
JSON sample file and resumes completed clips without opening a model. Phone audio
through a remote session is labeled separately from a local microphone.

The [remote sample plan](REMOTE_SAMPLE_PLAN.md) adds `run_samples.bat`, an explicit
fictional-test GUI that reuses the everyday controls while retaining started
recordings. Ordinary MyTranscribe still stores no clinical replay audio.

## Collect matched examples

Use fictional cases and the same microphone position for a paired normal-voice
and genuinely whispered recording of each example. Merely turning down an
existing waveform is a sensitivity test, not a whispered-speech test. Record
which microphone, Windows input level, connection, distance and microphone
processing features were used. Compare headset and conference microphones in
separate sessions rather than changing several variables together.

Start with about 20 new utterances in each group:

- Quick results/instructions: HGB, eGFR, comparison to prior, chest X-ray follow-up,
  numbered booking instructions and quote/newline commands.
- Complex exam/clinical notes: cerebellar examination, dysdiadochokinesia,
  Romberg, xerostomia, negation and changed/unchanged findings.
- Paragraph-style referrals: angina, surgery and other cases, 30–60 seconds,
  with explicit numbers, units, medication names and follow-up intervals.

Write the intended transcript independently of model output, including the
desired written abbreviations, paragraphs and list labels. Mark patient/doctor
names as ignored; medical eponyms such as Romberg remain scored clinical terms.
Preserve a held-out portion before changing vocabulary or prompt rules. The
existing local real-headset manifest format and trial tools can be reused;
recordings/transcripts belong only in ignored results directories.

## Measure capture before altering gain

For each clip, retain local signal-level summaries: RMS, peak/clipping rate,
silence decisions, duration and device configuration. Keep the feedback meter
visible in compact view and base it on the same captured PCM used for
transcription. If app-side gain is later introduced, measure and display the
post-gain waveform, while logging only numeric diagnostics.

First compare unchanged input, microphone/Windows gain changes, and the
microphone's processing settings. An automatic-gain candidate needs a bounded
gain, clipping prevention, noise/silence behavior and comparisons against the
unchanged recordings. A limiter or noise filter can also change speech; keep
each processing step independently selectable during the experiment. Evaluate
the existing RMS silence cutoff and Whisper VAD on quiet recordings as separate
variables, without guessing transcript content or weakening clinical-word checks.

## Score the whole workflow

Report per-group medical/common errors, clinical terms, numbers/units/negation,
formatting and warm Stop-to-formatted-text median/p95/max. Include cases shorter
than three seconds and realistic short messages, not only easy single words.
Also time start readiness, copy confirmation and paste usability separately
from engine delay. About a two-second finish delay for a brief instruction is
outside the desired workflow; longer letters can tolerate more delay when their
error rate improves.

Review actual changed clinical words, not just aggregate WER. A signal meter
shows capture level; it cannot guarantee that a whispered word was recognized.
Decide whether two recording modes are useful only if measurements demonstrate
a short-workflow advantage beyond what stopping a single 30-second workflow
already provides.
