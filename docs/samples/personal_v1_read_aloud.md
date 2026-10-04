# Personal dictation samples — set 1

Fourteen fictional examples: quick results, staff messages, complex examination notes and three paragraph referrals. Read the text naturally, including commands such as "new line", "new paragraph" and "open quotes". Say abbreviations as you normally do; the spaces in H G B simply indicate the letters. Do not read the sample number or category.

For a quick first pass, record 00, 03, 06, 07, 10 and 11 in your normal voice. Stop after each example. Later repeat 00, 06 and 10 with a genuine whisper, using the same device and position. This tests whispered speech rather than merely a quieter recording.

Samples 09, 12 and 13 are reserved for validation after changes chosen using the other examples. Record them now if convenient; keep their results separate from tuning.

## Record on this computer

The recorder can run independently of the coding agent. From the MyTranscribe
folder in PowerShell, use:

```powershell
.\venv1060\Scripts\python.exe .\scripts\record_snippets.py --script .\docs\samples\personal_v1.json --out .\results_1060\personal_v1_phone_normal --profile phone_remote_normal
```

Press Enter to start each clip, then Enter to stop. Press `r` and Enter to redo a
clip before accepting it, or `q` and Enter at the next prompt to stop the session.
Rerunning this command resumes the remaining clips. To replace accepted clips,
add `--redo 6` (or a comma-separated list). For just the six suggested starter
clips, add `--redo 0,3,6,7,10,11` on the first run.

For the three whispered pairs, use a separate folder and label:

```powershell
.\venv1060\Scripts\python.exe .\scripts\record_snippets.py --script .\docs\samples\personal_v1.json --out .\results_1060\personal_v1_phone_whisper --profile phone_remote_whisper --redo 0,6,10
```

For local headset recordings, replace `phone` / `phone_remote` in the folder and
profile labels with `headset`. Keep the microphone distance and input settings
consistent within a pair. Note the device, remote-access application, Windows
input level and any microphone processing settings separately.

Before using the phone, confirm that your voice reaches a Windows input device
and moves its microphone level indicator. A connected remote screen alone does
not establish that audio is reaching this computer. To list Windows inputs:

```powershell
.\venv1060\Scripts\python.exe .\scripts\record_snippets.py --list-devices
```

Add `--device N` to select the corresponding input. Phone-through-remote results
are scored as a separate capture condition from the local headset. The recorder
saves PCM WAVs and fixed-reference manifests in ignored local results folders;
it performs no recognition or network upload. The public JSON contains only
these fictional scripts and intended written references. It is recorder/scoring
data; it is not added to the production recognition prompt.

If you improvise or change a sentence, keep that recording separate and state
the intended wording. Freeze its reference before examining model output. For
the scripted comparison, say each example as written rather than correcting the
reference to match the transcription.

## 00 — result

H G B normal, e G F R similar to prior.

## 01 — result

Creatinine eighty six, potassium four point six. No change in renal function.

## 02 — result

T S H normal. Hemoglobin A one C six point eight, unchanged.

## 03 — message

Please call to tell him the chest X ray was normal. An appointment can be booked at my next available. New line. Open quotes. Recheck C X R, prior smoking, consider C T if still coughing. Close quotes.

## 04 — message

One period. Repeat C B C and ferritin in six weeks. New line. Two period. Book review after the results, any available spot.

## 05 — message

Please tell her no pneumonia was seen. New line. Open quotes. Persistent cough, review if not settling. Close quotes.

## 06 — exam

Cerebellar examination significant for dysdiadochokinesia, changed from the prior examination. Romberg unchanged. No nystagmus.

## 07 — exam

Two period. Xerostomia. Continue water based lubricants applied to the mucosa and the other strategies in the prior documentation. No oral candidiasis.

## 08 — exam

Well appearing. Abdomen S N T. No C V A tenderness. No guarding or rebound.

## 09 — exam (reserved validation)

Reduced pinprick sensation over the lateral calf. Ankle dorsiflexion four out of five on the right and five out of five on the left. No foot drop at rest.

## 10 — letter

Thank you for seeing this pleasant seventy two year old for assessment of exertional chest discomfort. Symptoms began while moving house last week and recur when walking uphill. They settle within five minutes of rest. There has been no pain at rest, syncope, or associated palpitations. New paragraph. Relevant history includes hypertension and dyslipidemia. Current medications include ramipril five milligrams daily and atorvastatin twenty milligrams nightly. Blood pressure today was one hundred and thirty two over seventy eight. The resting E C G showed sinus rhythm without acute ischemic changes. New paragraph. I would appreciate your assessment of possible angina and advice regarding further investigation.

## 11 — letter

Thank you for assessing this fifty eight year old with a symptomatic right inguinal hernia. He first noticed the swelling three months ago. It becomes more prominent with lifting and prolonged standing and reduces when lying down. There has been no vomiting, abdominal distension, or change in bowel habit. New paragraph. Examination today showed a reducible right inguinal hernia with a cough impulse. The abdomen was soft and nontender. There was no overlying erythema and no clinical evidence of incarceration. He takes apixaban five milligrams twice daily for atrial fibrillation. New paragraph. I would appreciate your opinion regarding elective repair and the perioperative management of his anticoagulation.

## 12 — result (reserved validation)

Platelets stable at one hundred and forty eight. No anemia.

## 13 — letter (reserved validation)

Thank you for reviewing this sixty six year old with persistent paresthesia in both feet. Symptoms have progressed gradually over six months, without weakness or a change in bladder function. She has not noticed symptoms in her hands. New paragraph. Examination demonstrated reduced vibration at the great toes and absent ankle reflexes bilaterally. Power was preserved. Her hemoglobin A one C was six point two, vitamin B twelve was two hundred and eighty, and thyroid function was normal. She takes levothyroxine seventy five micrograms daily for hypothyroidism. New paragraph. I would appreciate your assessment for possible peripheral neuropathy and advice on further investigation.


