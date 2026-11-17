# Dictation in Spanish, French and Swahili (2026-11-16)

Status: **experimental, with the same options as English.** Options → Speech model → Dictation language, or `MYTRANSCRIBE_LANGUAGE=es|fr|sw`. English is the default. No clinician has yet dictated into it in any of the three languages; the evidence below is public speech sets, computer voices, and one small set of real French medical dictation.

## Does it need another model?

Whisper large-v3 is one multilingual model: the app tells it the language and the same download serves all of them. Measured as the app runs it (int8_float16, beam 5, voice-activity filter) on the first 300 test sentences of [FLEURS](https://huggingface.co/datasets/google/fleurs) (Google, CC BY 4.0; read general text, many speakers):

| Language | Model | Word error rate | Character error rate |
|---|---|---|---|
| Spanish | standard large-v3 | 2.29% | 0.91% |
| French | standard large-v3 | 5.52% | 1.86% |
| Swahili | standard large-v3 | 38.67% | 13.06% |
| Swahili | large-v3 fine-tuned for Swahili | **20.49%** | 8.43% |

So Spanish and French need nothing extra. Swahili needs a tuned model: [`cdli/whisper-large-v3-swahili-afrivoice-cv`](https://huggingface.co/cdli/whisper-large-v3-swahili-afrivoice-cv) (Apache 2.0; a Kenyan research group's fine-tune of large-v3 on AfriVoice and Common Voice) nearly halves the errors on the same sentences. It is still the same software: `scripts/convert_whisper_model.py --repo cdli/whisper-large-v3-swahili-afrivoice-cv --language sw` downloads it once (6 GB) and converts it to the app's format (1.5 GB in `models_whisper/sw/`, ignored by git; needs the optional environment with torch). When that folder exists the app loads it for Swahili and goes back to the standard model for other languages; the switch took 1.7 s in the real window. One word in five wrong is still far from usable for clinical notes.

## The options, per language

| Option | Spanish | French | Swahili |
|---|---|---|---|
| Spoken formatting (paragraph, line, quotes) | yes | yes | yes |
| Spoken punctuation | yes | yes | yes |
| Pause-aware dictation (sentence carry, command recovery, post-roll) | yes | yes | yes |
| Extra corrections: readings (142/86, g/L), units, small numbers as digits | yes | yes | blood pressure and units |
| Extra corrections: medical term spelling | yes (135 terms, draft list) | yes (130 terms, draft list) | no (no word-frequency data to tell a real word from a misspelling) |
| Medical vocabulary prompt by topic | no (one fixed style example) | no | no |
| Validation tool (show, record, score) | yes, draft set | yes, draft set | no reading set |
| MedASR | English only | English only | English only |

How it is built: `src/lang_packs.py` holds, per language, the command phrases, the punctuation words and when such a word is an ordinary noun ("en coma", "un point de suture"), units, number words, a style prompt, and a medical term list (`src/vocab/medical_es.txt`, `medical_fr.txt`). `src/lang_commands.py` applies a pack; the pause-aware code takes its command phrases from the pack too. English keeps its own tuned code, and its vocabulary prompt and corrector are switched off for the other languages.

## The finding that mattered: show the model what dictation looks like

Whisper treats its prompt as the text that came before. With an ordinary style example, it wrote the punctuation words but often left out a spoken "nuevo párrafo" or "à la ligne" altogether, as an aside. Adding one short example of dictation with the commands spoken ("Paciente estable, punto. Nuevo párrafo. Sin fiebre, coma, …") fixed it. Development readings, pause-aware, punctuation on:

| | Layout right, ordinary prompt | Layout right, with the dictated example | Marks missing |
|---|---|---|---|
| Spanish (40 readings, 284 marks) | 26 | 40 | 19 → 1 |
| French (40 readings, 270 marks) | 18 | 39 | 20 → 5 |
| Swahili (20 readings, 123 marks, tuned model) | 16 | 20 | 20 → 6 |

The same idea was then tried in **English** and adopted there too (`voice_commands.DICTATION_EXAMPLE`, used when Spoken punctuation is on): on the fictional validation set, commands 39/40 → 40/40 and formatting 10/11 → 11/11; on the owner's own recordings, development commands 52/58 → 54/58 and formatting 11/13 → 12/13, held-out unchanged at 56/56 and 12/12, word errors 3.39% → 3.24% and 10.70% → 10.54%.

## How it was tested

There are no recordings of clinicians dictating punctuation in Spanish or Swahili, and no Spanish or Swahili medical speech set was found. So:

- **Synthetic dictated speech** (`scripts/lang_reliability.py`): published sentences from the FLEURS transcripts (not the 300 used for the baseline), three to an item with a paragraph or line break, turned into their dictated form and read by open-source [Piper](https://github.com/OHF-Voice/piper1-gpl) voices (two each for Spanish and French, one for Swahili). Split into development items, used to write the packs, and held-out items, run once. The draft medical reading sets were read the same way ("medical"); those were seen while writing the term lists, so they count as development.
- **Real French dictation:** the French part of Corti Med-Dictate (7 notes, 1,532 words, clinicians dictating every mark), run **once** at the end. Evaluation only, as its licence requires; the French pack was written before it was opened and not changed afterwards.
- **Real French medical speech:** MultiMed (MIT), 344 clips. Not dictation.

| Set | Word error rate, punctuation option off → on | Marks missing | Command words left in the text | Layout right |
|---|---|---|---|---|
| Spanish held-out, synthetic (34 readings) | 14.34% → 2.94% | 1 of 224 | 2 | 34 of 34 |
| Spanish medical draft, synthetic (20) | 19.61% → 2.99% | 2 of 120 | 0 | 19 of 20 |
| French held-out, synthetic (22) | 13.99% → 4.56% | 2 of 130 | 0 | 20 of 22 |
| French medical draft, synthetic (20) | 19.44% → 4.76% | 4 of 124 | 1 | 20 of 20 |
| Swahili held-out, synthetic (5, tuned model) | 32.04% → 20.77% | 0 of 35 | 0 | 5 of 5 |
| **French, Corti real dictation (7 notes)** | **32.96% → 8.68%** | not scored | 0 of 267 | not scored |

MultiMed French came out at 33% word errors. It is short clips of conversation and lectures with loose transcripts ("ah tiens ça c'est…"), a different task from dictation; it says the model is not good at that, and nothing was tuned on it.

In the real app window (file audio played in real time as the microphone): a Spanish item came out exactly as its text, Options → Swahili loaded the tuned model, and back to English restored the English model, prompt and corrector.

## Real French prescriptions (PxCorpus)

[PxCorpus](https://huggingface.co/datasets/bastiendechamps/px-corpus) (CC BY 4.0) is spoken drug prescriptions in French: "Kardégic 75 mg, un comprimé par jour pendant un mois". Real people, no dictated punctuation. Its development split (283 recordings, 39 speakers, experts and non-experts) was used to find problems; its test split (570 recordings by 14 doctors) was run once at the end.

Its transcripts are unaccented, write "1" for "un" and spell units out, so a plain word comparison charges the app for writing "mg". `lang_reliability.py files --prescriptions` scores with units, small numbers, accents, hyphens, "%" and the filler "euh" made the same on both sides; drug names are compared as written.

| Development split | Word error rate |
|---|---|
| Plain comparison, first run | 24.0% |
| Fair comparison, same output | 13.9% |
| + "incomprimé" → "1 comprimé", invented closing lines removed | 11.8% |
| + French brand names in the term list | 11.5% |
| + a prescription line in the style prompt | 9.1% |
| **Test split, run once** | **10.7%** |

What the development recordings showed, all now handled in the French pack:

- "un comprimé" was heard as "incomprimé" in about one prescription in ten.
- A brand name that opens the recording was often dropped or mangled; an example prescription in the prompt fixed most of that.
- A trailing "euh" sometimes produced an invented "Sous-titrage …" line (a known Whisper habit in French); such closing lines are removed.

What remains is mostly brand and generic names the model has not met ("praziquantel" → "prasicantel", "Deroxat" → "déoxyde"); the corpus's own spellings are annotators' ("efiline" for Euphylline), so some of those are not errors. The same prescription line was added to the Spanish prompt by analogy and checked only for doing no harm on the synthetic sets.

## More real and synthetic sets (searched in Spanish and French too)

| Set | Language | What it is | Result |
|---|---|---|---|
| [TEME-v1](https://zenodo.org/records/17280661) (CC BY 4.0) | Spanish | 90 synthetic doctor-patient dialogues, ten specialties, 37,000 words | 4.7% word errors as written; 4.3% with number words and units compared fairly |
| Dictées médicales ultra complexes (no licence stated: evaluation only) | French | 107 synthetic medical dictations, 22 specialties, 5.5 hours | development part (30): 20.7% fair before the changes below, 18.0% after; held part (77), run once: 22.7% as written, 19.9% fair |

- `lang_reliability.py files --fair` writes number words as digits (2 to 1000, French and Spanish tables in the script) and units as abbreviations on both sides before comparing, so "soixante-trois milligrammes" and "63 mg" count as the same.
- **Spanish (TEME):** after fair scoring the commonest real errors are "tensión" heard as "atención", "TAC" as "tag", and a few drug names. No changes made from it yet.
- **French dictations, worked on 2026-11-17 (branch `dictation/french`):** on the development part the errors that survived fair scoring were the letter opening written in the plural ("Chers confrères"), "créatininémie" cut to "créatinine", "l'ECG" as "le CG", "FEVG" as "FEV", and units written out or run together ("mmHg" as "mg", "g/L" as "gl"). What changed in the French pack:
  - the style prompt now opens "Cher confrère," and carries an ECG and a laboratory line with units as they are written (µmol/L, mmol/L, g/dL, mg/L, mmHg); the prescription line is kept whole, because shortening it cost a point on the real prescriptions (9.2% → 10.4%);
  - units after a number: "micromoles", "nanogrammes", "picogrammes", "litres", "millimètres de mercure", and "par minute" as a rate (2 L/min); after a pressure the unit is mmHg whatever was written; "gl", "mgl", "gdl" after a number → g/L, mg/L, g/dL; "165-80" → 165/80;
  - 17 terms added to the list (kaliémie, natrémie, créatininémie, ferritine, …).

  | French, word error rate | Before | After |
  |---|---|---|
  | Medical dictations, development part (fair) | 20.7% | 18.0% |
  | Medical dictations, held part (fair), run once | not run | 19.9% |
  | Real prescriptions, PxCorpus development | 9.1% | 9.2% |
  | Synthetic dictated speech, held-out (22) | 4.6% | 5.0% |
  | Synthetic dictated speech, medical draft (20) | 4.9% | 5.3% |

  The two synthetic sets are about 1,100 words each; the half-point is four or five words, all names and homophones that flip from run to run ("Carpanedo", "T-Rex", "débuter / débutez"), with nothing traceable to the new rules. The Corti French set was not run again (its runs are rationed).
- **A bug found on the way, fixed for every language:** an invented subtitle line ("Sous-titrage ST' 501") in the middle of a text made the clean-up delete everything after it, hundreds of dictated words in two development recordings. Only the invented sentence is removed now, and only when it opens a sentence.
- **Why the dictation figures stay near 20%:** the recordings are synthetic and several contain stretches of 8 to 10 s of loud noise where words should be; the model's voice filter rightly drops them and the reference words count as errors. A second listen to those stretches with the filter off was tried and produced invented subtitle lines, so it was not kept. The titles also differ by style ("Monsieur" written "M.", "Docteur" as "Dr"), which is how the app is asked to write them.
- **Found but unusable:** the Kiswahili ASR challenge evaluation set (audio only, transcripts unpublished), PixVoice French healthcare speech (audio without its transcript files) and the WannaMedASR French benchmark (score reports only).
- **Not found:** any open recording of clinicians dictating in Spanish. Two papers say the same; one built its audio by text-to-speech over Spanish clinical text.
- **Waiting on access:** AfriSwitchCare (Swahili-English clinical conversations, non-commercial) and AfriVox-v2, requested by the owner.

## Limits

- **Computer voices and one small real set.** The Corti French result is the only evidence from people dictating, and it is 7 notes from that dataset's speakers. Spanish and Swahili have none.
- **Extra marks.** With punctuation on, the model still adds some commas of its own that the speaker did not dictate (17 extra on 224 marks, Spanish held-out). Harmless mostly, but it is not strictly "what was dictated".
- **Drafts by an AI assistant:** the packs, the Spanish and French term lists and the reading sets. They need a clinician who dictates in the language; regional usage (Spain / Latin America, France / Canada) is not considered. The Swahili pack has not been reviewed by a Swahili speaker; one phrase was added from how the model heard the voice ("haya mpya").
- **The Swahili voice is Congolese Swahili, the tuned model Kenyan,** and the held-out set is 5 readings.
- **French homophones** (débuter / débutez, serais / serai) are the largest remaining French word errors; they are grammar, not vocabulary, and nothing here addresses them.
- **No Dragon comparison** in any of the three languages.
- **Licences to read before use at work:** the Swahili model (Apache 2.0), FLEURS (CC BY 4.0), Piper voices (each has its own; used here only to make test audio), Corti (evaluation only).

## Reproduce

```powershell
# recognition baseline
python scripts\fleurs_benchmark.py --root results_1060\fleurs --languages es_419,fr_fr,sw_ke --limit 300
# synthetic dictated speech for one language (needs piper-tts and the voices)
python scripts\lang_reliability.py make  --language es --fleurs results_1060\fleurs --voices results_1060\piper_voices --out results_1060\lang\es
python scripts\lang_reliability.py run   --language es --out results_1060\lang\es --split held
python scripts\lang_reliability.py score --language es --out results_1060\lang\es --split held
```
