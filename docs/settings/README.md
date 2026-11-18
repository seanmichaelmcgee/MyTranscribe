# Settings development

Where the app's defaults and the setup wizard's choices come from, and the rules for changing
them. The test material behind them is in [../testing/](../testing/README.md).

## Where things are

- [SETTINGS_SUITE.md](SETTINGS_SUITE.md): the mission: anyone close to the owner's accuracy
  after five minutes of setup, and the milestones to get there.
- [SETUP_WIZARD_PLAN.md](SETUP_WIZARD_PLAN.md): the wizard and tuning to a voice. Phase 1 is
  built; phases 2–5 are plans.
- **Code:**
  - `src/settings.py`: every option and its default;
  - `src/setup_wizard.py`, `src/mic_check.py`: the wizard and the microphone check;
  - `src/options_dialog.py`: Options.
- **Named settings for testing:** `PROFILES` in `scripts/dictation_reliability.py`.
- **The settings suite and its test voices:**
  [../testing/SYNTHETIC_VOICES.md](../testing/SYNTHETIC_VOICES.md).

## Judgments so far

1. **Tune only the few things the measurements support.** Those are:
   - how the person dictates punctuation;
   - their usual medications;
   - their microphone and its level;
   - a handful of word fixes.

   Beam size, silence detection, window length and rewriting the style prompt measured within
   noise, or were risky. Evidence: [BENCHMARKS.md](../BENCHMARKS.md) and
   [optimization/](../optimization/).
2. **Ask how the person dictates, then check it.** The wrong punctuation answer is the costliest
   error found: 44.9% vs 14.2% word errors on Corti.
3. **Rules for changing a setting.** A change is kept only if:
   - it gives at least 2 fewer errors, and at least 10% fewer, on the tuning items;
   - it is no worse on the checking items;
   - it adds no new clinical error (drug, number, dose, unit, frequency, negation, layout).

   Defaults win ties.
4. **Tuning and checking items are fixed before any result is seen.**
5. **Synthetic voices propose; real voices confirm.** No default changes on synthetic evidence
   alone.
6. **Every change can be explained and undone.** Setup keeps a backup of the replaced
   settings. Existing installs are never sent through the wizard.

## Another language

The wizard's questions and the rules above carry over. The language pack supplies the mark
words and commands. Which settings are worth tuning has to be measured again in each language,
not assumed from English.
