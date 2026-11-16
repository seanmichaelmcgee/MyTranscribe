# Validating MyTranscribe against Dragon on your own voice

Two stages. Stage 1 uses invented text and is safe to analyse with any tool,
including an AI assistant. Stage 2 is real dictation and must never leave the PC.

## Stage 1: the fictional reading set (available now)

`validation/validation_set_v1.txt` holds 28 invented items: 20 short messages
("Please let her know the X-ray was okay.") and 8 consult letters of three or four
paragraphs (the problem, past history and medications, examination, thanks). About
1,200 words, 10 to 15 minutes of reading. No real person is described.

You read each item once. Dragon types into the tool's window while the tool records
the same microphone; afterwards the saved audio goes through Whisper and then MedASR,
and all three are scored against the text you were asked to read.

```powershell
# what you will be asked to say (dictated words in CAPITALS)
venv1060\Scripts\python.exe scripts\validation_tool.py show

# the reading session: a window; Dragon must be running
venv1060\Scripts\python.exe scripts\validation_tool.py record --out results_1060\validation\session1

# afterwards: Whisper, then MedASR (if installed), then the comparison
venv1060\Scripts\python.exe scripts\validation_tool.py score --out results_1060\validation\session1
```

For each item: **Start** (button or F8), switch Dragon's microphone on, read the item
including the words in CAPITALS ("PERIOD", "COMMA", "NEW PARAGRAPH", "OPEN QUOTE"),
switch Dragon's microphone off, wait until Dragon has finished typing, **Stop** (F8).
Keep the cursor in the Dragon box; the tool puts it there for you. Read numbers and
units naturally ("5 mg" as "five milligrams", "142 over 86"). **Redo this item** if you
stumble. You can close the window and carry on later: finished items are kept.

The Dragon box is a standard Windows edit control on purpose: Dragon does not type
into text boxes it does not recognise.

Output, all inside the `--out` folder (`results_1060/` is ignored by git):

- `items\<id>.wav` and `items\<id>.dragon.txt`: your recording and what Dragon typed
- `local_whisper.json`, `local_medasr.json`: what each local recogniser wrote
- `results.json`, `results.csv`: per-item word errors, formatting and last-word checks,
  and totals for short items, consult letters and everything

Because the audio is kept, a later build can be scored on the same reading without
you reading again: delete `local_*.json` and run `score` once more.

### How the score is computed, and how far to trust it

- **Word error rate** counts substituted, missing and extra words against the item's
  text, after lower-casing and removing punctuation marks. Punctuation is judged
  separately: *format ok* compares paragraph breaks, line breaks, quotes and list
  numbers; *commands* counts the dictated formatting that arrived.
- The comparison is mechanical. It does not know that "5 mg" and "five milligrams"
  mean the same, so a recogniser that writes the other form is charged an error. The
  app's Extra corrections write numbers and units the way the set does, and Dragon
  does by default, which keeps this small; the results note records how many of the
  flagged differences on this set were real mistakes when read by a person.
- One reading per item. Differences of a word or two between systems on 1,200 words
  are noise; look for a gap of a percentage point or more, and at which kind of item
  it comes from.
- The set dictates every mark, as you do with Dragon. Whisper is run with pause-aware
  dictation, spoken punctuation and Extra corrections on; MedASR with the text
  options on.

## Stage 2: real dictation, counts only (design; not built yet)

The aim is the same comparison on what you actually dictate, with nothing readable
left behind and nothing transmitted.

- **During a dictation** MyTranscribe listens to the same microphone as Dragon and
  transcribes in memory. No audio is written.
- **When the note is final** you paste the text you kept. The scorer compares
  MyTranscribe's text (and Dragon's first draft, if you paste that too) with it, writes
  one line of numbers (date, word count, error counts by kind, whether formatting
  matched) and discards all three texts.
- **Presumed, not true, error rate.** Your final text began as Dragon's output, so a
  Dragon mistake you did not correct counts against MyTranscribe. The useful figures
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
