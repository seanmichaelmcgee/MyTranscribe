"""
make_test_dictation.py — synthetic, fictional primary-care dictations for testing.

Creates spoken test letters (no real patient data) from templates whose drug,
diagnosis and test slots are filled from src/vocab/primary_care.txt, renders
them with text-to-speech, and simulates several microphones:

  clean       TTS output as-is
  headset     close-talking mic: faint noise (SNR 35 dB)
  conference  far-field conference mic ~1.5 m away (e.g. a Tenor-style puck):
              room reverb (RT60 0.45 s), HVAC noise (SNR 22 dB), mains hum,
              100 Hz-7 kHz band limit
  noisy       busy clinic room: more reverb (RT60 0.6 s) + background
              voices (babble, SNR 12 dB)

Output folder:  <out>/<scenario>__<profile>.wav, <out>/<scenario>.txt (reference),
                <out>/manifest.json (files, references, target terms),
                <out>/read_aloud/*.txt (scripts you can read into your real mic)

TTS backends: "sapi" (Windows built-in voices, no install needed) or "espeak"
(espeak-ng). TTS mispronounces some drug names, so absolute accuracy here is a
pessimistic floor; use it to COMPARE settings, and the read_aloud scripts with
your own voice for real numbers.

  python scripts/make_test_dictation.py --out testdict
  python scripts/eval_dictation.py --manifest testdict/manifest.json
"""

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from vocab import load_lexicon  # noqa: E402

SR = 16000

# Slots: {a|b|c} picks one of the listed options (curated to stay clinically
# coherent); {topic:category} picks any term of that category from the
# vocabulary file (used only where every member is plausible). Each pick
# becomes a target term for term-recall scoring. Text is written the way it is
# *spoken* (no "b.i.d."), with digits for numbers. All patients are fictional.
TEMPLATES = {
    "fm_diabetes_htn": (
        "Dear Doctor Patel. Thank you for seeing this 58-year-old man with type 2 diabetes mellitus and "
        "{essential hypertension|hypertension} complicated by {diabetic nephropathy|microalbuminuria}. "
        "His most recent hemoglobin A1c was 8.4 percent despite metformin 1000 milligrams twice daily and "
        "{gliclazide|sitagliptin|linagliptin}. Blood pressure in clinic was 152 over 94 on {hypertension:drug}. "
        "His urine albumin to creatinine ratio is elevated and his eGFR is 54. We discussed adding "
        "{empagliflozin|dapagliflozin|canagliflozin} for cardiorenal protection, and {semaglutide|dulaglutide|tirzepatide} "
        "for weight. I have arranged retinal screening and ordered {lipid panel|apolipoprotein B} testing. "
        "I would be grateful for your advice. Kind regards."),
    "fm_cardiac": (
        "Dear Doctor Chen. I am referring a 71-year-old woman with new {atrial fibrillation|atrial flutter}, "
        "found on a routine ECG. She reports palpitations and mild exertional dyspnea. Her CHA2DS2-VASc score is 4. "
        "I have started {apixaban|rivaroxaban|edoxaban} and {metoprolol|bisoprolol|diltiazem} for rate control. "
        "Recent bloodwork showed a normal {NT-proBNP|troponin} and a TSH within range. "
        "An {echocardiogram} and a {Holter monitor|event monitor} have been booked. Thank you for seeing her."),
    "im_copd": (
        "Assessment. 66-year-old with COPD, 40 pack-years, now with an acute exacerbation of COPD. "
        "Increased sputum purulence and wheeze for 5 days. Oxygen saturation 91 percent on room air. "
        "Plan. Prednisone 40 milligrams daily for 5 days and {doxycycline|amoxicillin-clavulanate|azithromycin} for 5 days. "
        "Continue {salbutamol|albuterol} as needed and switch {tiotropium|umeclidinium-vilanterol} to "
        "{fluticasone-umeclidinium-vilanterol|Trelegy Ellipta}. Repeat {spirometry} once recovered "
        "and refer to pulmonary rehabilitation. {varenicline|Champix} offered for smoking cessation."),
    "im_ckd_gout": (
        "Follow-up note. Chronic kidney disease stage 3b with an eGFR of 38 and recurrent {gout|tophaceous gout}. "
        "Current medications include {allopurinol|febuxostat}, {furosemide|hydrochlorothiazide} and "
        "{atorvastatin|rosuvastatin}. Uric acid remains 520. We will titrate the urate-lowering therapy slowly with "
        "{colchicine} prophylaxis and check {creatinine|electrolytes} in 4 weeks. Avoid nonsteroidal "
        "anti-inflammatory drugs. A {renal ultrasound} showed no hydronephrosis."),
    "fm_mental_health": (
        "Mental health follow-up. 34-year-old with {major depressive disorder} and {generalized anxiety disorder|panic disorder}. "
        "PHQ-9 today is 16 and GAD-7 is 12. She did not tolerate {sertraline|citalopram} because of nausea. "
        "We will start {escitalopram|venlafaxine|vortioxetine|desvenlafaxine} at a low dose and continue "
        "{trazodone|mirtazapine} at night for sleep. No suicidal ideation. Referral for cognitive behavioural "
        "therapy has been sent. Review in 4 weeks."),
    "fm_womens_health": (
        "Dear Doctor Okafor. Thank you for seeing this 29-year-old with {polycystic ovary syndrome|endometriosis} "
        "and {heavy menstrual bleeding|dysmenorrhea}. She is currently using {drospirenone|norethindrone} for contraception. "
        "A {pelvic ultrasound|transvaginal ultrasound} showed a 4 centimetre left ovarian cyst. "
        "Her {beta-hCG|urine pregnancy test} was negative. We discussed a "
        "{levonorgestrel intrauterine system|Mirena|Kyleena} as an alternative, and {tranexamic acid} for heavy days. "
        "Many thanks for your assessment."),
    "peds_bronchiolitis": (
        "Pediatric note. 7-month-old with 3 days of cough, coryza and increased work of breathing, consistent with "
        "{bronchiolitis}. Respiratory rate 52 with mild subcostal indrawing and nasal flaring. "
        "Oxygen saturation 95 percent. Feeding at two thirds of normal with 4 wet diapers today. "
        "{nasopharyngeal swab|viral panel} was positive for {respiratory syncytial virus}. Supportive care, nasal saline "
        "and small frequent feeds. She did not receive {nirsevimab|Beyfortus} this season. "
        "Immunizations are otherwise up to date including {Pediacel|Infanrix hexa} and {Prevnar 20|PCV20}."),
    "peds_croup_aom": (
        "Assessment. 3-year-old with a barking cough and stridor at rest overnight, consistent with "
        "{croup|laryngotracheobronchitis}. Westley croup score 3. Given {dexamethasone} 0.6 milligrams per kilogram "
        "by mouth with good effect. Right tympanic membrane bulging and erythematous, in keeping with "
        "{acute otitis media}. Started {amoxicillin|high-dose amoxicillin} 90 milligrams per kilogram per day "
        "divided twice daily for 10 days. {acetaminophen} and {ibuprofen} as needed for fever."),
    "peds_wellchild": (
        "18-month well-child visit. Growth along the 50th percentile for weight and length, head circumference "
        "on the 75th percentile. Developmental milestones appropriate, walking well, 10 words. "
        "{Rourke Baby Record|Nipissing District Developmental Screen|Ages and Stages Questionnaire} completed and "
        "{M-CHAT-R} negative. History of {positional plagiocephaly|nasolacrimal duct obstruction|cow's milk protein allergy}, "
        "now resolved. Received {MMRV|Priorix-Tetra|ProQuad} and {DTaP-IPV-Hib|Pediacel} today. Anticipatory guidance "
        "on safe sleep, car seat use and {fluoride varnish|iron-fortified cereal}. Next visit at 2 years."),
    "peds_derm_asthma": (
        "Dear Doctor Singh. I am referring this 9-year-old with moderate {atopic dermatitis} and persistent asthma. "
        "Eczema has not responded to {mometasone cream|betamethasone valerate} or {tacrolimus ointment|pimecrolimus|crisaborole}. "
        "For asthma she uses {fluticasone|budesonide|ciclesonide} with an {AeroChamber} and {salbutamol|Ventolin} as needed. "
        "She also has {allergic rhinitis} treated with {cetirizine|desloratadine|bilastine}. I wondered whether she "
        "might be a candidate for {dupilumab|Dupixent}. Thank you for seeing her."),
}

_SLOT_RE = re.compile(r"\{([^{}]+)\}")


def fill_template(template: str, lexicon, rng: random.Random):
    """Fill {a|b} and {topic:category} slots. Returns (text, target_terms)."""
    used, terms = set(), []

    def pick(m):
        body = m.group(1)
        if ":" in body and "|" not in body and body.split(":")[0] in lexicon.topics:
            topic, cat = body.split(":", 1)
            pool = [x.text for x in lexicon.topics[topic].terms if x.category == cat
                    and x.text.lower() not in used and not re.search(r"\d|/", x.text)]
            if not pool:
                raise SystemExit(f"vocabulary has no unused '{cat}' terms in topic '{topic}'")
        else:
            pool = [o.strip() for o in body.split("|") if o.strip().lower() not in used] or body.split("|")
        choice = rng.choice(pool)
        used.add(choice.lower())
        terms.append(choice)
        return choice
    text = _SLOT_RE.sub(pick, template)
    text = re.sub(r"(^|[.!?] )([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text, terms


# ── TTS ──────────────────────────────────────────────────────────────────────
_PS_SAPI = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($env:MT_VOICE) { $s.SelectVoice($env:MT_VOICE) }
$s.Rate = [int]$env:MT_RATE
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$s.SetOutputToWaveFile($env:MT_OUT, $fmt)
$s.Speak([IO.File]::ReadAllText($env:MT_TEXT))
$s.Dispose()
"""


def sapi_voices():
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis."
                          "SpeechSynthesizer).GetInstalledVoices() | % { $_.VoiceInfo.Name }"],
                         capture_output=True, text=True, timeout=60)
    return [v.strip() for v in out.stdout.splitlines() if v.strip()]


def tts(text: str, out_wav: Path, backend: str, voice: str = "", rate: int = 0):
    """Render text to 16 kHz mono 16-bit WAV."""
    import os
    with tempfile.TemporaryDirectory() as td:
        txt = Path(td) / "t.txt"
        txt.write_text(text, encoding="utf-8")
        if backend == "sapi":
            env = dict(os.environ, MT_OUT=str(out_wav), MT_TEXT=str(txt), MT_VOICE=voice, MT_RATE=str(rate))
            subprocess.run(["powershell", "-NoProfile", "-Command", _PS_SAPI], env=env, check=True, timeout=300)
        else:
            raw = Path(td) / "raw.wav"
            cmd = ["espeak-ng", "-v", voice or "en-us", "-s", str(150 + 10 * rate), "-f", str(txt), "-w", str(raw)]
            subprocess.run(cmd, check=True, timeout=300)
            audio, sr = read_wav(raw)
            write_wav(out_wav, resample(audio, sr, SR))


def read_wav(path: Path):
    with wave.open(str(path), "rb") as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def write_wav(path: Path, audio: np.ndarray):
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def resample(a: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return a
    n = int(round(len(a) * sr_out / sr_in))
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)


# ── Microphone / room simulation ─────────────────────────────────────────────
def pink_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    spec[1:] /= np.sqrt(f[1:])
    spec[0] = 0
    x = np.fft.irfft(spec, n)
    return (x / (np.std(x) + 1e-12)).astype(np.float32)


def room_ir(rt60: float, drr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Direct path + a few early reflections + exponentially decaying diffuse tail."""
    n = int(SR * rt60 * 1.2)
    t = np.arange(n) / SR
    tail = rng.standard_normal(n) * 10 ** (-3 * t / rt60)
    tail[: int(0.004 * SR)] = 0                          # tail starts after 4 ms
    for delay_ms, gain in ((7, 0.5), (13, 0.35), (21, 0.25)):
        tail[int(delay_ms * SR / 1000)] += gain * np.sqrt(np.sum(tail ** 2) / max(1, n)) * 50
    tail *= 1 / (np.sqrt(np.sum(tail ** 2)) + 1e-12) * 10 ** (-drr_db / 20)
    ir = tail.astype(np.float32)
    ir[0] = 1.0
    return ir


def fft_convolve(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = len(x) + len(h) - 1
    size = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(h, size), size)[: len(x)]
    return y.astype(np.float32)


def band_limit(x: np.ndarray, lo: float, hi: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    gain = np.clip((f - lo * 0.5) / (lo * 0.5), 0, 1) * np.clip((hi * 1.15 - f) / (hi * 0.15), 0, 1)
    return np.fft.irfft(spec * gain, len(x)).astype(np.float32)


def speech_rms(x: np.ndarray) -> float:
    """RMS over the louder half of 20 ms frames (ignores pauses)."""
    frame = int(0.02 * SR)
    usable = len(x) // frame * frame
    if usable == 0:
        return float(np.sqrt(np.mean(x ** 2)) + 1e-9)
    e = np.sqrt(np.mean(x[:usable].reshape(-1, frame) ** 2, axis=1))
    return float(np.mean(np.sort(e)[len(e) // 2:]) + 1e-9)


def add_at_snr(x: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    noise = noise[: len(x)]
    gain = speech_rms(x) / (np.sqrt(np.mean(noise ** 2)) + 1e-12) / 10 ** (snr_db / 20)
    return x + noise * gain


def normalize(x: np.ndarray, target_dbfs: float = -22) -> np.ndarray:
    x = x * (10 ** (target_dbfs / 20) / speech_rms(x))
    peak = np.max(np.abs(x))
    return x / peak * 0.95 if peak > 0.95 else x


PROFILES = ("clean", "headset", "conference", "noisy")


def apply_profile(x: np.ndarray, profile: str, seed: int, babble_sources=()) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if profile == "clean":
        return normalize(x)
    if profile == "headset":
        return normalize(add_at_snr(band_limit(x, 80, 7800), pink_noise(len(x), rng), 35))
    if profile == "conference":
        y = fft_convolve(x, room_ir(0.45, drr_db=3, rng=rng))
        t = np.arange(len(y)) / SR
        hum = sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((60, 120, 180), 1)).astype(np.float32)
        y = add_at_snr(y, pink_noise(len(y), rng), 22)
        y = add_at_snr(y, hum, 40)
        return normalize(band_limit(y, 100, 7000))
    if profile == "noisy":
        y = fft_convolve(x, room_ir(0.6, drr_db=0, rng=rng))
        babble = np.zeros(len(y), np.float32)
        for src in babble_sources:
            s = src[::-1]                                   # reversed speech: voice-like, unintelligible
            reps = int(np.ceil(len(y) / max(1, len(s))))
            babble += np.roll(np.tile(s, reps)[: len(y)], int(rng.integers(0, len(y))))
        if not babble.any():
            babble = pink_noise(len(y), rng)
        y = add_at_snr(y, babble, 12)
        y = add_at_snr(y, pink_noise(len(y), rng), 25)
        return normalize(band_limit(y, 100, 7000))
    raise ValueError(profile)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Make synthetic fictional dictation test audio.")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--backend", choices=["sapi", "espeak"],
                    default="sapi" if sys.platform == "win32" else "espeak")
    ap.add_argument("--voice", default="", help="SAPI voice name or espeak voice (default: system default)")
    ap.add_argument("--rate", type=int, default=0, help="speech rate -3..3 (0 = normal)")
    ap.add_argument("--profiles", default=",".join(PROFILES))
    ap.add_argument("--scenarios", default="all", help="comma list of template names, or 'all'")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args(argv)

    if args.list_voices:
        print("\n".join(sapi_voices() if args.backend == "sapi" else ["see: espeak-ng --voices=en"]))
        return 0
    if args.backend == "espeak" and not shutil.which("espeak-ng"):
        raise SystemExit("espeak-ng not found (on Windows use --backend sapi)")

    lex = load_lexicon()
    rng = random.Random(args.seed)
    names = list(TEMPLATES) if args.scenarios == "all" else args.scenarios.split(",")
    profiles = [p.strip() for p in args.profiles.split(",") if p.strip()]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "read_aloud").mkdir(exist_ok=True)

    clean = {}
    texts = {}
    for name in names:
        text, terms = fill_template(TEMPLATES[name], lex, rng)
        texts[name] = (text, terms)
        (args.out / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        (args.out / "read_aloud" / f"{name}.txt").write_text(
            "Read at your normal dictation pace (fictional patient):\n\n" + text + "\n", encoding="utf-8")
        raw = args.out / f"{name}__tts.wav"
        tts(text, raw, args.backend, args.voice, args.rate)
        clean[name], _ = read_wav(raw)
        raw.unlink()

    manifest = []
    for i, name in enumerate(names):
        others = [clean[n] for n in names if n != name][:4]
        text, terms = texts[name]
        for j, profile in enumerate(profiles):
            audio = apply_profile(clean[name], profile, seed=args.seed * 1000 + i * 10 + j, babble_sources=others)
            wav = args.out / f"{name}__{profile}.wav"
            write_wav(wav, audio)
            manifest.append({"audio": wav.name, "scenario": name, "profile": profile,
                             "reference": text, "terms": terms, "seconds": round(len(audio) / SR, 1)})
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total = sum(m["seconds"] for m in manifest)
    print(f"Wrote {len(manifest)} files ({total / 60:.1f} min of audio) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
