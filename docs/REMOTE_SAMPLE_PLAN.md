# Phone and remote-session sample plan

## What happened in the local check

The user reported that the app worked well, including the input bar and appearance.
The 4 October app log records one combined 34.816-second session: a 26.731-second
chunk transcribed in 3.51 seconds and an 8.085-second remainder in 1.60 seconds.
It then reports a successful 559-character copy. Copy was logged about 35 ms after
the final chunk finished; the exact Stop event was not logged, so this is not an
exact Stop-to-text measurement.

The ordinary app retained no replay WAV. Completed chunks leave its capture buffer,
and idle pre-roll holds only the latest half second. Both Windows and Qt clipboard
checks returned empty. No fresh transcript or audio was recovered into a results
file, and no recognition error score or MedASR rerun can be derived from this session.
The existing app was left open rather than discarding its displayed transcript.
If that text is still present, it can be copied on return for a qualitative review.

The wrong launcher was used for retaining an evaluation recording. The dedicated
test launcher below closes that workflow gap; ordinary clinical capture remains
in memory.

## On return: use the test window

1. If useful, expand the existing app with **+** and preserve its last transcript.
   Then close ordinary MyTranscribe so that one app uses the microphone and GPU.
2. Connect the phone microphone through the chosen remote application. Confirm
   that speaking into it moves a Windows input indicator. Select that input as
   the Windows default **before** launching the test app. If the microphone route
   changes later, close and reopen the test app.
3. Double-click **`run_samples.bat`** in the MyTranscribe folder. The window title
   and persistent banner say **FICTIONAL TEST CAPTURE**. This mode saves local
   audio and text when a dictation is started; idle microphone audio is not saved.
4. Choose **Phone normal**, select a sample, wait for Ready, and use the large
   Start/Stop button. F9 hold and the configured mouse control are also available.
   Read the displayed text naturally, including spoken formatting commands.
5. Wait for **Test saved locally**, then choose another sample or repeat. Each
   attempt receives a unique file name; a repeat preserves the earlier attempt.
6. For matched whispered samples, choose **Phone whisper** and repeat **00, 06
   and 10**, keeping position and microphone settings constant.

After recording, close the test window so the next engine comparison can use the
GPU. The test window holds the same exclusive lock as the comparison runner,
preventing another test window or locked benchmark from loading concurrently.

For a quick first pass, use individual samples **00, 03, 06, 07, 10 and 11**.
The first drop-down option also offers **Combined starters** (00/03/06/07), with
explicit **New paragraph** commands between examples. It is scored as one combined
recording; it cannot establish finishing latency for separate short snippets.
Individual samples give the more useful short-workflow comparison.

If the remote connection does not deliver microphone audio to Windows, record
the same examples in the phone's voice recorder and transfer the original audio
files to this computer. Preserve those as a separate phone capture condition.
Phone keyboard dictation produces text before MyTranscribe receives it; that
does not test either local recognition engine.

For phone voice files without a remote microphone connection, follow the
[phone-file guide](PHONE_FILE_PLAN.md). The local importer preserves the original
and prepares matched audio for both engines, with separate phone-file conditions.

## Data and comparison

Test artifacts stay under ignored `results_1060/personal_v1_capture`: PCM 16 kHz
mono WAVs, a manifest with the fixed sample reference and profile, and adjacent
app-output diagnostics. An interrupted recording is not published as a completed
manifest entry. Confirm each intended reference before scoring; readings that
include a changed sentence or sample heading need an independent corrected reference.

The sample text is recorder/reference data. Recognition uses the existing
production prompts, without receiving the intended answer. This test adapter
adds no model or package and forces offline model loading. Its own UI settings
are stored separately from normal application settings.

Next comparison: run the saved waveform through the current Whisper baseline
and the existing MedASR configurations sequentially, preserving model, source,
configuration and corpus fingerprints. Review medical words, ordinary words,
numbers/negation and formatting, alongside finishing delay. Phone normal,
phone whisper and local-headset results remain separate. Samples **09, 12 and
13** remain reserved for validation after choices made on the other samples.

The previous runtime scorecards retain their original source fingerprints. This
capture/shutdown work is not a new ASR accuracy measurement. Fresh saved samples
are needed before claiming an accuracy improvement.

## Validation of the capture change

**444 tests passed in 30.44 seconds.** Tests verify exact PCM retention, complete
WAV publication, frozen references, distinct repeats, capture-time selection
locking and rejection of changed source. The test layout was inspected using a
simulated engine and no microphone/GPU. The existing run-lock implementation is
reused for the dedicated test application's lifetime.

Testing exposed an existing chime close/playback race. Chime cleanup now waits
for the playing stream to close before terminating its audio device; playback
requested after cleanup cannot reopen it. Output failures also close the stream.
The checks simulate concurrent playback/shutdown and failed output without an
audio device. No recognition setting or package changed.

The original application remains open. The new capture launcher has been prepared,
not started alongside it. Its real-microphone run awaits the next user recording.
