# Validating MyTranscribe against your current dictation software, on your own voice

Two stages. Stage 1 uses invented text and is safe to analyse with any tool,
including an AI assistant. Stage 2 is real dictation and must never leave the PC.

## Stage 1: the fictional reading set (available now)

`validation/validation_set_v1.txt` holds 28 invented items: 20 short messages
("Please let her know the X-ray was okay.") and 8 consult letters of three or four
paragraphs (the problem, past history and medications, examination, thanks). About
1,200 words, 10 to 15 minutes of reading. No real person is described.

You read each item once. Your other dictation software, if you use one, types into the
tool's window while the tool records
the same microphone; afterwards the saved audio goes through Whisper and then MedASR,
and all three are scored against the text you were asked to read.

```powershell
# what you will be asked to say (dictated words in CAPITALS)
venv1060\Scripts\python.exe scripts\validation_tool.py show

# the reading session: a window; start your other dictation software first, if you compare with one
venv1060\Scripts\python.exe scripts\validation_tool.py record --out results_1060\validation\session1

# afterwards: Whisper, then MedASR (if installed), then the comparison
venv1060\Scripts\python.exe scripts\validation_tool.py score --out results_1060\validation\session1
```

For each item: **Start** (button or F8), switch the other software's microphone on, read the item
including the words in CAPITALS ("PERIOD", "COMMA", "NEW PARAGRAPH", "OPEN QUOTE"),
switch its microphone off, wait until it has finished typing, **Stop** (F8).
Keep the cursor in the text box; the tool puts it there for you. Read numbers and
units naturally ("5 mg" as "five milligrams", "142 over 86"). **Redo this item** if you
stumble. You can close the window and carry on later: finished items are kept.

The text box is a standard Windows edit control on purpose: desktop dictation software often does not type
into text boxes it does not recognise.

Output, all inside the `--out` folder (`results_1060/` is ignored by git):

- `items\<id>.wav` and `items\<id>.other.txt`: your recording and what the other software typed
- `local_whisper.json`, `local_medasr.json`: what each local recogniser wrote
- `results.json`, `results.csv`: per-item word errors, formatting and last-word checks,
  and totals for short items, consult letters and everything

Because the audio is kept, a later build can be scored on the same reading without
you reading again: delete `local_*.json` and run `score` once more.

### Recording somewhere else (shared Google Drive folder)

The Google Drive folder "MyTranscribe validation" holds the reading script and a `recordings`
folder. On any machine, start **one** recording with the headset you dictate with and read
straight through, saying **"break break"** between items. If you stumble, say "sorry, break
break" and read that item again; the later reading counts. Put the recording in `recordings`
under any name, in any common audio format; several recordings are fine. Nothing needs naming
or ordering: `import` cuts the audio at each "break break" and matches every piece to its item
by what was said. (Files named by item code, `s01.m4a`, and the `items` folder written by this
tool's `record` window, with its `<code>.other.txt` files, are accepted too.) On the analysis
machine, where Google Drive for desktop shows the folder as `G:\My Drive\MyTranscribe validation`:

```powershell
python scripts\validation_tool.py import --from "G:\My Drive\MyTranscribe validation\recordings" --out results_1060\validation\session1
python scripts\validation_tool.py score  --out results_1060\validation\session1
```

Only the fictional reading material belongs in that folder. Real dictation must never be put
there: the stage 2 rules below apply to it.

### Other languages

Draft Spanish and French sets are in `validation/validation_set_es_v1.txt` and
`validation_set_fr_v1.txt`. Add `--set validation\validation_set_es_v1.txt` to `show` and
`record` and `score`; the dictated words are shown in that language, and `score` runs Whisper
with that language's pack and reports word errors, marks and layout. They are drafts written by an AI
assistant and need a clinician who dictates in the language to read them first.

### How the score is computed, and how far to trust it

- **Word error rate** counts substituted, missing and extra words against the item's
  text, after lower-casing and removing punctuation marks. Punctuation is judged
  separately: *format ok* compares paragraph breaks, line breaks, quotes and list
  numbers; *commands* counts the dictated formatting that arrived.
- The comparison is mechanical. It does not know that "5 mg" and "five milligrams"
  mean the same, so a recogniser that writes the other form is charged an error. The
  app's Extra corrections write numbers and units the way the set does, and the commercial reference
  does by default, which keeps this small; the results note records how many of the
  flagged differences on this set were real mistakes when read by a person.
- One reading per item. Differences of a word or two between systems on 1,200 words
  are noise; look for a gap of a percentage point or more, and at which kind of item
  it comes from.
- The set dictates every mark, as many clinicians do with desktop dictation software. Whisper is run with pause-aware
  dictation, spoken punctuation and Extra corrections on; MedASR with the text
  options on.

### First real reading (2026-11-16)

The owner read the set in one 8.5-minute recording with spoken breaks (26 of 28 items; the
first two were not on the recording). It was cut into 26 clips, all matched, including one
item restarted after "sorry, break break".

| | WER | Adjusted WER | Format ok | Commands | Last words ok | Drug names | Doses |
|---|---|---|---|---|---|---|---|
| Commercial reference | 4.83% | 4.50% | 10/10 | 37/37 | 25/26 | 23/24 | 14/15 |
| Whisper large-v3, all options | 2.08% | 2.00% | 10/10 | 37/37 | 26/26 | 24/24 | 15/15 |
| MedASR, text options | 5.83% | 5.25% | 10/10 | 37/37 | 25/26 | 24/24 | 14/15 |

- **The commercial reference** heard the same 26 clips, played through the virtual cable into its microphone
  input with Notepad in front; its text was read from Notepad after each clip. It is the
  owner's own trained profile, but a recording played back, not the live microphone.
- **Where the commercial reference's errors are:** about a third are surnames ("Verhoeven" as "very hoven",
  "Kowalczyk" as "cholecystic"), plus "formoterol" as "for what to roll" and dropped or
  changed small words. Whisper's are small words and two surnames.
- **About nine differences are shared by the commercial reference and Whisper** ("131" as "113", "with" as
  "but", "symptoms" as "sweats", "day" as "night"). Two systems agreeing against the script
  means the reader most likely said it that way, so both true rates are a little lower.
- **Before the drug-name correction** (`src/drug_names.py`, part of Extra corrections) Whisper
  stood at 3.00% with 22/24 drug names and 14/15 doses: "Ram and Pearl" for ramipril,
  "4-Motorol" for formoterol, and "75 mg micrograms". All three are now right.
- **Then two more fixes** took Whisper from 2.50% to 2.08% with every heading and command
  right: the "Plan" heading that had been lost is kept (a word left alone at the end of an
  audio chunk is now handed to the next chunk), and "I'd be grateful" / "There's no" are
  written out as dictated.
- **In the number format a 6 GB GTX card uses** (int8_float32) the same 26 clips score the
  same 2.08%, and the app used about 3.7 GB of video memory at its peak.
- **How the commercial run was made to work:** it typed nothing into the tool's own window or
  into its own dictation box on this day; after it was restarted it typed into Notepad. The
  microphone was switched on once and left on, so no key was sent between clips.
- Getting the cut right mattered: before the clips were kept clear of the break words and of
  an abandoned false start, Whisper's figure read 4.3%.

Reading every difference, punctuation included (50 in all), showed what matters for someone
who dictates every mark:

- **Commas nobody said.** A dozen were commas the model added by itself ("normal, with no
  murmurs"). Options → "Only the commas I dictate" (`MYTRANSCRIBE_ONLY_DICTATED_COMMAS=1`, off
  by default) removes those and keeps the spoken ones, as desktop dictation software does.
- **Small numbers as words** before nouns the number rule did not know ("two blocks", "one
  flight", "two falls"); those nouns were added.
- With both, the differences fall from 50 to 35; word error rate, which ignores punctuation
  and number style, was unchanged by these two at 3.00%.
- What was left then was recognition: surnames, three drug names (since fixed, see above),
  "I'd" for "I would", and one lost "Plan". Starting with vocabulary topics switched on
  (`MYTRANSCRIBE_VOCAB_TOPICS`) fixed "A1c" but not ramipril, and made no difference overall
  (3.08%): not adopted.

### Second reading: letters with drug names (2026-11-17)

Set v2 (`validation/validation_set_v2.txt`, about 5 minutes): two consult letters and three short
messages with drugs in running prose. The owner dictated it at the desk into MyTranscribe and
the commercial reference while recording; the recording was split and scored as before. Whisper, personal profile:
2.44% before the fixes it led to, 1.22% after, with every drug name right. What was found and
changed is in `docs/optimization/2026-11-15-dictation-reliability.md` ("Owner's dictated letters").

### Self-test of the tool and the scorer (2026-11-16)

Before anyone read the set, a Windows text-to-speech voice read all 28 items through
a virtual audio cable, with the commercial reference typing into the tool and the tool
recording the same audio. This proves the tool end to end; it says little about your
voice, and a computer voice is easier than a person.

| | WER | Adjusted WER | Format ok | Commands | Last words ok |
|---|---|---|---|---|---|
| Commercial reference | 2.47% | 2.14% | 11/11 | 40/40 | 27/28 |
| Whisper large-v3, all options | 1.15% | 0.82% | 10/11 | 39/40 | 28/28 |
| MedASR, text options | 2.63% | 2.05% | 11/11 | 40/40 | 26/28 |

Every flagged difference was then read (the text is invented, so that is safe):

- Commercial reference 30 flagged, 4 not mistakes; Whisper 14 flagged, 4 not mistakes; MedASR 32
  flagged, 7 not mistakes. The non-mistakes were all of two kinds: a British or
  American spelling or "ok"/"okay", and one word written as two ("long-standing" /
  "longstanding", "breastbone" / "breast bone", "follow-up" / "followup"). The
  **adjusted** column no longer counts those; nothing else is forgiven.
- What remains is real: people's names (all three; MedASR dropped most of them),
  drug names (the commercial reference wrote Ativan for apixaban, Whisper "mg" for "mcg" once), and a
  few small words. Two name spellings no listener could know (Whitcomb/Whitcombe,
  Denis/Dennis) are still counted.
- So expect the plain figure to overstate errors by roughly a quarter to a third at
  these low error rates, and the adjusted figure to be close to what a reader would
  count.
- Whisper left out a spoken "open quote" twice and a "new paragraph" once. The
  missing opening quote is now restored when the closing one follows a dictated
  break; the missing paragraph break is the one formatting miss in the table.

## Stage 2: real dictation, counts only (design; not built yet)

The aim is the same comparison on what you actually dictate, with nothing readable
left behind and nothing transmitted.

- **During a dictation** MyTranscribe listens to the same microphone as your other dictation software and
  transcribes in memory. No audio is written.
- **When the note is final** you paste the text you kept. The scorer compares
  MyTranscribe's text (and the other software's first draft, if you paste that too) with it, writes
  one line of numbers (date, word count, error counts by kind, whether formatting
  matched) and discards all three texts.
- **Presumed, not true, error rate.** Your final text began as the other software's output, so a
  mistake of its that you did not correct counts against MyTranscribe. The useful figures
  are the trend and the cases where the two disagree.
- **Privacy rules for stage 2**
  - The scorer is local code with no network access; the recognisers already run
    offline. To enforce it, block that `python.exe` from outbound connections in
    Windows Firewall, or run a session with the network unplugged.
  - No audio or text file is kept. Only the numbers file exists afterwards.
  - **Never let an AI assistant (including Claude) open real transcripts or audio.**
    Anything it reads is sent to its provider. Run the tool yourself; share only the
    numbers file, which contains no words from the notes.
  - The mechanical scorer is the one validated on the fictional set in stage 1, used
    unchanged, so its accuracy is known before it meets real notes.
