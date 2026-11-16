# Dictation in Spanish, French and Swahili: first step (2026-11-16)

Status: **experimental.** Options → Speech model → Dictation language, or `MYTRANSCRIBE_LANGUAGE=es|fr|sw`. English is the default and is unchanged. Nothing here has been tried with a clinician dictating in any of the three languages.

## What was measured

Whisper large-v3 exactly as the app runs it (int8_float16, beam 5, voice-activity filter, no prompt), with the language set, on the first 300 test sentences of each language from [FLEURS](https://huggingface.co/datasets/google/fleurs) (Google, CC BY 4.0; evaluation only). FLEURS is read general text, about 10 seconds a sentence, many speakers. It measures how well the model hears the language, not medical dictation.

| Language | Audio | Word error rate | Character error rate | Sentences with ≤ 10% errors |
|---|---|---|---|---|
| Spanish (Latin America) | 62 min | 2.29% | 0.91% | not counted |
| French | 52 min | 5.52% | 1.86% | 234 of 300 |
| Swahili (Kenya) | 71 min | 38.67% | 13.06% | 9 of 300 |

Scoring is lower-cased words without punctuation against the published transcript, numbers as written ("12" against "douze" is an error), so every figure is a little pessimistic. Compute was about 3 minutes per language on the RTX 4070 Ti SUPER. `scripts/fleurs_benchmark.py` reproduces it.

**Reading:** Spanish and French recognition is already good; what they lacked was everything after recognition. Swahili is a different problem: the output is recognisably Swahili but more than one word in three is wrong (misspelt stems, words split or joined), and no formatting rule can repair that.

## What was built

- **Dictation language** setting, passed to Whisper. Switching does not reload the model.
- **Language packs** (`src/lang_packs.py`): per language, the phrases that are formatting commands, the words that are punctuation marks, when such a word is an ordinary noun instead, units, and a short style prompt. `src/lang_commands.py` applies a pack. English keeps its own tuned code untouched.

| | Spanish | French | Swahili |
|---|---|---|---|
| New paragraph / line | punto y aparte, nuevo párrafo / nueva línea | nouveau paragraphe / à la ligne | aya mpya / mstari mpya |
| Marks | punto, coma, dos puntos, punto y coma, abrir/cerrar interrogación | point, virgule, deux points, point-virgule, point d'interrogation | nukta, koma, nukta mbili, nukta mkato, alama ya kuuliza |
| Quotes | abrir / cerrar comillas → "…" | ouvrez / fermez les guillemets → « … » | fungua / funga nukuu |
| Stays an ordinary word | "en coma", "coma diabético", "un punto de sutura", "a punto de", "dos puntos de sutura" | "un point de suture", "sur le point de", "ne … point", "deux points de suture" | "njia ya mkato" |
| Conventions | decimal comma ("5 coma 4" → 5,4); "142 sobre 86" → 142/86; mg, g/L, % | space before : ; ? !; "142 sur 86" → 142/86 ("14 sur 8" is left as said) | "120 kwa 80" → 120/80 |

- **English aids are switched off** for another language: the English medical vocabulary prompt, the drug-name spelling corrector and the word check would otherwise "correct" Spanish or French words towards English terms. The pack's own style prompt is used instead. There is no medical vocabulary for these languages yet.
- **MedASR** is English-only; with it selected the language setting is ignored and Options says so.
- **Draft reading sets** `validation/validation_set_es_v1.txt` and `validation_set_fr_v1.txt` (8 short messages and 2 consult letters each). `scripts/validation_tool.py --set <file>` shows and records them with the dictated words in that language. A test checks that what each item asks you to say converts back to exactly its text, which caught three rule mistakes while writing them.

## What is not known

- **How Whisper writes a dictated mark in Spanish or French.** In English it sometimes writes the word, sometimes the mark, sometimes drops a command. The packs accept the word with or without punctuation around it, but they have never met real audio: this PC has no Spanish or French voice to synthesise a test, and no recordings. The first real reading of the draft sets is the test.
- **The reading sets and packs were written by an AI assistant.** Spanish and French are languages it handles well, but wording, abbreviations and regional usage (Spain vs Latin America, France vs Canada) need a clinician who dictates in them. The Swahili pack has not been reviewed by a Swahili speaker at all; every phrase in it should be checked.
- **Medical vocabulary** in these languages (drug names, in particular brand names) is untested. FLEURS has none.
- **No comparison system.** Dragon Medical One was not run in any of these languages.

## Swahili: what would actually be needed

1. A model that hears Swahili well. The usual route is Whisper fine-tuned on Swahili speech (Mozilla Common Voice has a large Swahili collection); that is training work with its own data and licence review, and its result should be measured on the same 300 sentences first.
2. Mixed language. Clinical Swahili is commonly mixed with English drug names and terms; a single-language setting handles that poorly. It needs recordings from real speakers to measure.
3. A native-speaking clinician to write the reading set and to judge errors. The author cannot check Swahili medical text reliably.

No Swahili reading set is included for that reason.
