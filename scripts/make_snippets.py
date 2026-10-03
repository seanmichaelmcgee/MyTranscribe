"""
make_snippets.py — short fictional clinical snippets in three workflow styles, as audio.

  message  short instructions to staff, with voice commands ("new line", quotes)
  result   very short lab/imaging comments ("renal normal, hemoglobin similar")
  exam     physical-exam fragments with spoken shorthand ("abdomen S N T", "C V A")
  letter   referral letters with numbered items ("new line, 1 period, ...")

Each snippet has the spoken text (what the TTS voice says), the expected written
text (after voice commands), and key terms to check. Rendered with Windows SAPI
voices through the headset and conference-mic simulations of make_test_dictation.
All content is fictional.

    venv1060\\Scripts\\python.exe scripts\\make_snippets.py --out results_1060\\snippets
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import make_test_dictation as mtd   # noqa: E402

# (category, spoken, expected written text, key terms)
SNIPPETS = [
    ("message",
     "Please call and tell him his x-ray is normal and book review in two weeks, any spot. "
     "New line. Open quote. Follow up x-ray. Close quote.",
     'Please call and tell him his x-ray is normal and book review in 2 weeks, any spot.\n"Follow up x-ray".',
     ["x-ray", "review in 2 weeks"]),
    ("message",
     "Please let her know the ultrasound was normal and no follow up is needed. New line. "
     "Recall in one year for her routine physical.",
     "Please let her know the ultrasound was normal and no follow up is needed.\n"
     "Recall in 1 year for her routine physical.",
     ["ultrasound", "routine physical"]),
    ("message",
     "Call to advise the potassium was slightly high at five point four. Repeat the lab next week. "
     "New line. Open quote. Repeat potassium and creatinine. Close quote.",
     'Call to advise the potassium was slightly high at 5.4. Repeat the lab next week.\n'
     '"Repeat potassium and creatinine".',
     ["potassium", "5.4", "creatinine"]),
    ("message",
     "Tell mom the throat swab was negative, so stop the amoxicillin. "
     "Book a review if the fever lasts more than three days.",
     "Tell mom the throat swab was negative, so stop the amoxicillin. "
     "Book a review if the fever lasts more than 3 days.",
     ["throat swab", "amoxicillin"]),
    ("message",
     "The A1c improved to seven point one. Continue metformin. New paragraph. "
     "Follow up in three months with a repeat A1c.",
     "The A1c improved to 7.1. Continue metformin.\n\nFollow up in 3 months with a repeat A1c.",
     ["A1c", "7.1", "metformin"]),
    ("message",
     "Please book a phone visit this week to review the echo. New line. Open quote. Echo review. Close quote.",
     'Please book a phone visit this week to review the echo.\n"Echo review".',
     ["phone visit", "echo"]),
    ("message",
     "Advise the urine culture grew E. coli sensitive to nitrofurantoin. "
     "Start nitrofurantoin one hundred milligrams twice daily for five days.",
     "Advise the urine culture grew E. coli sensitive to nitrofurantoin. "
     "Start nitrofurantoin 100 mg twice daily for 5 days.",
     ["urine culture", "E. coli", "nitrofurantoin", "100 mg"]),
    ("message",
     "Let him know the PSA is stable at one point two. Repeat in one year.",
     "Let him know the PSA is stable at 1.2. Repeat in 1 year.",
     ["PSA", "1.2"]),
    ("result", "Renal normal, hemoglobin similar.", "Renal normal, hemoglobin similar.", ["renal", "hemoglobin"]),
    ("result", "Lipids improved, L D L one point eight.", "Lipids improved, LDL 1.8.", ["lipids", "LDL", "1.8"]),
    ("result", "T S H normal, no change.", "TSH normal, no change.", ["TSH"]),
    ("result", "Ferritin low at twelve, start iron.", "Ferritin low at 12, start iron.", ["ferritin", "iron"]),
    ("result", "I N R two point four, therapeutic, same dose.", "INR 2.4, therapeutic, same dose.",
     ["INR", "2.4", "therapeutic"]),
    ("result", "C B C normal. Lytes normal.", "CBC normal. Lytes normal.", ["CBC", "lytes"]),
    ("result", "Creatinine stable, e G F R fifty eight.", "Creatinine stable, eGFR 58.", ["creatinine", "eGFR", "58"]),
    ("result", "B twelve normal, vitamin D low.", "B12 normal, vitamin D low.", ["B12", "vitamin D"]),
    ("result", "Chest x-ray clear.", "Chest x-ray clear.", ["chest x-ray"]),
    ("result", "Urinalysis negative.", "Urinalysis negative.", ["urinalysis"]),
    ("exam",
     "Presented for cough but noted to have C V A tenderness. Abdomen S N T, well appearing overall.",
     "Presented for cough but noted to have CVA tenderness. Abdomen SNT, well appearing overall.",
     ["cough", "CVA", "SNT"]),
    ("exam", "Chest clear bilaterally, no wheeze. Heart sounds normal, no murmur. J V P not elevated.",
     "Chest clear bilaterally, no wheeze. Heart sounds normal, no murmur. JVP not elevated.",
     ["bilaterally", "murmur", "JVP"]),
    ("exam", "H E E N T normal. T M's clear bilaterally. Throat mildly erythematous, no exudate.",
     "HEENT normal. TMs clear bilaterally. Throat mildly erythematous, no exudate.",
     ["HEENT", "TMs", "erythematous", "exudate"]),
    ("exam", "Abdomen soft, non-tender, no guarding. Murphy's sign negative.",
     "Abdomen soft, non-tender, no guarding. Murphy's sign negative.", ["non-tender", "guarding", "Murphy"]),
    ("exam", "Alert, N A D, well perfused. Cap refill under two seconds.",
     "Alert, NAD, well perfused. Cap refill under 2 seconds.", ["NAD", "cap refill"]),
    ("exam", "Right knee effusion, no erythema. Full range of motion, ligaments stable.",
     "Right knee effusion, no erythema. Full range of motion, ligaments stable.",
     ["effusion", "erythema", "range of motion"]),
    ("exam", "Erythematous papules on the trunk, no vesicles.",
     "Erythematous papules on the trunk, no vesicles.", ["erythematous", "papules", "vesicles"]),
    ("exam", "Cranial nerves two to twelve intact, power five out of five throughout.",
     "Cranial nerves 2 to 12 intact, power 5 out of 5 throughout.", ["cranial nerves"]),
    ("exam", "Mild pedal edema bilaterally, pitting to the ankle.",
     "Mild pedal edema bilaterally, pitting to the ankle.", ["pedal edema", "pitting"]),
    # Letters to colleagues, with numbered items said the user's way: "new line, 1 period, ...".
    ("letter",
     "Dear Dr. Okafor, Thank you for seeing Ms. Lena Brooks, a 46-year-old woman with recurrent right upper "
     "quadrant pain after fatty meals over the past four months. Ultrasound shows multiple gallstones with a "
     "normal common bile duct and no gallbladder wall thickening. Liver enzymes and lipase are normal. "
     "New line. 1 period. Symptomatic cholelithiasis. I would appreciate your assessment for laparoscopic "
     "cholecystectomy. New line. 2 period. Type 2 diabetes, well controlled on metformin one thousand milligrams "
     "twice daily, A1c six point eight. New line. 3 period. Hypertension on amlodipine five milligrams daily. "
     "New paragraph. Thank you for your help with her care. Kind regards.",
     "Dear Dr. Okafor, Thank you for seeing Ms. Lena Brooks, a 46-year-old woman with recurrent right upper "
     "quadrant pain after fatty meals over the past 4 months. Ultrasound shows multiple gallstones with a "
     "normal common bile duct and no gallbladder wall thickening. Liver enzymes and lipase are normal.\n"
     "1. Symptomatic cholelithiasis. I would appreciate your assessment for laparoscopic cholecystectomy.\n"
     "2. Type 2 diabetes, well controlled on metformin 1000 mg twice daily, A1c 6.8.\n"
     "3. Hypertension on amlodipine 5 mg daily.\n\nThank you for your help with her care. Kind regards.",
     ["right upper quadrant", "gallstones", "common bile duct", "lipase", "cholelithiasis",
      "laparoscopic cholecystectomy", "metformin", "A1c", "amlodipine"]),
    ("letter",
     "Dear Dr. Haddad, I would be grateful if you could see Mr. Victor Nguyen, a 61-year-old man with exertional "
     "chest pressure for six weeks, relieved by rest within five minutes. He has no rest pain or syncope. "
     "E C G shows sinus rhythm with no acute changes, and troponin was negative. New line. 1 period. Suspected "
     "stable angina. I have started aspirin eighty one milligrams daily, bisoprolol two point five milligrams "
     "daily and nitroglycerin spray as needed. New line. 2 period. Dyslipidemia, L D L three point four, now on "
     "rosuvastatin twenty milligrams. New line. 3 period. Former smoker, thirty pack years. New paragraph. "
     "I would appreciate your opinion on an exercise stress test or C T coronary angiography. Kind regards.",
     "Dear Dr. Haddad, I would be grateful if you could see Mr. Victor Nguyen, a 61-year-old man with exertional "
     "chest pressure for 6 weeks, relieved by rest within 5 minutes. He has no rest pain or syncope. ECG shows "
     "sinus rhythm with no acute changes, and troponin was negative.\n1. Suspected stable angina. I have started "
     "aspirin 81 mg daily, bisoprolol 2.5 mg daily and nitroglycerin spray as needed.\n2. Dyslipidemia, LDL 3.4, "
     "now on rosuvastatin 20 mg.\n3. Former smoker, 30 pack years.\n\nI would appreciate your opinion on an "
     "exercise stress test or CT coronary angiography. Kind regards.",
     ["exertional chest pressure", "ECG", "sinus rhythm", "troponin", "stable angina", "aspirin", "bisoprolol",
      "nitroglycerin", "dyslipidemia", "LDL", "rosuvastatin", "exercise stress test", "CT coronary angiography"]),
    ("letter",
     "Dear Dr. Chen, Thank you for seeing Mrs. Alice Moreau, a 58-year-old woman with eight months of dry eyes "
     "and dry mouth, and intermittent parotid swelling. Her A N A is positive with anti Ro antibodies. "
     "New line. 1 period. Dry eyes. Start lubricating drops four times daily. New line. 2 period. Xerostomia. "
     "Start water based lubricant and sugar free lozenges. New line. 3 period. Suspected Sjogren's syndrome. "
     "I would value your assessment. Kind regards.",
     "Dear Dr. Chen, Thank you for seeing Mrs. Alice Moreau, a 58-year-old woman with 8 months of dry eyes "
     "and dry mouth, and intermittent parotid swelling. Her ANA is positive with anti-Ro antibodies.\n"
     "1. Dry eyes. Start lubricating drops 4 times daily.\n2. Xerostomia. Start water-based lubricant and "
     "sugar-free lozenges.\n3. Suspected Sjogren's syndrome. I would value your assessment. Kind regards.",
     ["dry eyes", "parotid", "ANA", "anti-Ro", "lubricating drops", "xerostomia", "water-based lubricant",
      "lozenges"]),
]
PROFILES = ("headset", "conference")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "results_1060" / "snippets")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    voices = mtd.sapi_voices() or [""]
    manifest = []
    for i, (cat, spoken, written, terms) in enumerate(SNIPPETS):
        raw = args.out / f"_raw_{i:02d}.wav"
        mtd.tts(spoken, raw, "sapi", voice=voices[i % len(voices)])
        audio, sr = mtd.read_wav(raw)
        audio = mtd.resample(audio, sr, mtd.SR)
        raw.unlink()
        lead = mtd.np.zeros(int(0.3 * mtd.SR), mtd.np.float32)        # a breath before speaking
        audio = mtd.np.concatenate([lead, audio, lead])
        for j, prof in enumerate(PROFILES):
            name = f"{i:02d}_{cat}__{prof}.wav"
            mtd.write_wav(args.out / name, mtd.apply_profile(audio, prof, seed=100 * i + j))
            manifest.append({"audio": name, "scenario": f"{i:02d}_{cat}", "category": cat, "profile": prof,
                             "spoken": spoken, "reference": written, "terms": terms,
                             "seconds": round(len(audio) / mtd.SR, 1)})
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    secs = [m["seconds"] for m in manifest if m["profile"] == PROFILES[0]]
    print(f"Wrote {len(manifest)} files to {args.out}; snippet length {min(secs)}-{max(secs)} s")


if __name__ == "__main__":
    main()
