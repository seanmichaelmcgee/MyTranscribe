"""voice_commands: spoken formatting, as Whisper actually punctuates it (fictional text)."""

import pytest

from voice_commands import apply


@pytest.mark.parametrize("raw, want", [
    # The user's own example, as Whisper typically writes it.
    ("Please call and tell him his x-ray is normal and book review in 2 weeks, any spot. "
     "New line, open quotes, follow up x-ray, close quotes.",
     'Please call and tell him his x-ray is normal and book review in 2 weeks, any spot.\n'
     '"Follow up x-ray".'),
    ("Plan as above. New paragraph. Thank you for seeing her.",
     "Plan as above.\n\nThank you for seeing her."),
    ("Renal normal, hemoglobin similar. Next line. Repeat in 3 months.",
     "Renal normal, hemoglobin similar.\nRepeat in 3 months."),
    ("He said, open quote, I feel fine, end quote, and left.",
     'He said, "I feel fine", and left.'),
    ("new line Lisinopril 10 mg daily.", "Lisinopril 10 mg daily."),
    ("Continue metformin. New line", "Continue metformin."),
])
def test_commands(raw, want):
    assert apply(raw) == want


@pytest.mark.parametrize("raw, want", [
    # The user's own way of dictating a numbered list, in the forms Whisper writes it.
    ("Plan as follows. New line, 1 period, dry eyes. Start lubricating drops. "
     "New line, 2 period, xerostomia. Start water-based lubricant.",
     "Plan as follows.\n1. Dry eyes. Start lubricating drops.\n2. Xerostomia. Start water-based lubricant."),
    ("Plan. New line. 2. Period. Xerostomia.", "Plan.\n2. Xerostomia."),
    ("Plan. New line, two period, xerostomia.", "Plan.\n2. Xerostomia."),
    ("Plan. New line, number 3 period, follow up in 6 weeks.", "Plan.\n3. Follow up in 6 weeks."),
    ("1 period, refer to general surgery.", "1. Refer to general surgery."),
    # Real-speech forms (user's recordings, 2026-10-03).
    ("Dry eyes. New line, 2 periods, xerostomia, start lubricant.", "Dry eyes.\n2. Xerostomia, start lubricant."),
    ("Dry eyes.\n2. 2 periods, xerostomia.", "Dry eyes.\n2. Xerostomia."),
])
def test_numbered_items(raw, want):
    assert apply(raw) == want


@pytest.mark.parametrize("text", [
    "Her last period was 2 weeks ago.",
    "She had 2 periods of chest pain this week.",
    "Take 1 tablet daily for a period of 2 weeks.",
    "We will start a new line of therapy if this fails.",
    "There is a new line on the chest film that was not there before.",
    "Patient is quite open to the plan.",
    "Abdomen soft, non-tender, well appearing overall.",
    "",
])
def test_ordinary_text_untouched(text):
    assert apply(text) == text


def test_idempotent():
    once = apply("Review in 2 weeks. New line, open quotes, CBC, close quotes.")
    assert apply(once) == once


@pytest.mark.parametrize("raw, want", [
    # The model lost its punctuation for a stretch (seen with long thinking pauses).
    ("chest is clear new paragraph the abdomen is soft",
     "chest is clear.\n\nThe abdomen is soft"),
    ("no new rash new paragraph Continue iron 300 mg daily", "no new rash.\n\nContinue iron 300 mg daily"),
    ("Renal normal hemoglobin similar new line repeat in 3 months",
     "Renal normal hemoglobin similar\nRepeat in 3 months"),
    ("Plan as above. New paragraph. Thank you for seeing her.", "Plan as above.\n\nThank you for seeing her."),
    # A clinical heading after "new line" (synthetic set item s04, 2026-11-18).
    ("no prednisone this year new line on examination her chest was clear",
     "no prednisone this year\nOn examination her chest was clear"),
])
def test_lenient_accepts_unpunctuated_breaks(raw, want):
    assert apply(raw, lenient=True) == want


def test_lenient_new_line_right_after_a_dictated_full_stop():
    raw = "no prednisone this year period new line on the left the chest was clear period"
    assert apply(raw, lenient=True, punctuation=True) == \
        "no prednisone this year.\nOn the left the chest was clear."
    raw = "this year full stop new line on examination her chest was clear full stop"
    assert apply(raw, lenient=True, punctuation=True) == "this year.\nOn examination her chest was clear."
    # "period" as a noun is not a full stop, so the noun guard still applies after it
    raw = "her last period new line of therapy was started"
    assert apply(raw, lenient=True, punctuation=True) == raw


def test_a_dictated_comma_keeps_a_term_that_holds_a_digit():
    assert apply("Seen today comma A1c 7.2 percent, B12 normal period", punctuation=True) == \
        "Seen today, A1c 7.2 percent, B12 normal."
    assert apply("The chest is clear, comma. It was fine, period.", punctuation=True) == \
        "The chest is clear, it was fine."


@pytest.mark.parametrize("text", [
    "We will start a new line of therapy if this fails.",
    "There is a new line on the chest film that was not there before.",
    "the new line was placed in the right internal jugular",
    "consider second line or new line of treatment",
    "Her last period was 2 weeks ago.",
    "Patient is quite open to the plan.",
    "There was a new line on examination of the film.",
])
def test_lenient_still_leaves_ordinary_text(text):
    assert apply(text, lenient=True) == text


def test_default_is_not_lenient():
    raw = "chest is clear new paragraph the abdomen is soft"
    assert apply(raw) == raw


# -- Spoken punctuation marks (punctuation=True) ------------------------------
@pytest.mark.parametrize("raw, want", [
    ("HENT normal period. TMs clear bilaterally period. Throat red comma, no exudate period.",
     "HENT normal. TMs clear bilaterally. Throat red, no exudate."),
    ("Medication review colon, ramipril 5 mg daily remains comma, no change period",
     "Medication review: ramipril 5 mg daily remains, no change."),
    ("HENT normal period tympanic membranes clear", "HENT normal. Tympanic membranes clear"),
    ("Chest X-ray clear full stop", "Chest X-ray clear."),
    ("Repeat creatinine. period. He agrees.", "Repeat creatinine. He agrees."),
    ("a rash semicolon, it does not say anaphylaxis period.", "a rash; it does not say anaphylaxis."),
    ("Is he fasting question mark. yes", "Is he fasting? Yes"),
    ("follow hyphen up in 2 weeks open paren, sooner if worse close paren, period.",
     "follow-up in 2 weeks (sooner if worse)."),
    ("eGFR is 58 period. Potassium 4.1 period.", "eGFR is 58. Potassium 4.1."),
    ("a 2 week period of observation period.", "a 2 week period of observation."),
    ("stopped last month period. The cough resolved period.", "stopped last month. The cough resolved."),
    ("the sigmoid colon is normal period. Plan colon, colonoscopy.", "the sigmoid colon is normal. Plan: colonoscopy."),
    ("any spot period. New line. 1 period. Angina period. New line, two period, Dyslipidemia comma, on statin period.",
     "any spot.\n1. Angina.\n2. Dyslipidemia, on statin."),
    ("Open quote. Take with food period. Close quote.", '"Take with food".'),
    ("the X-ray was okay period new paragraph open quote X-ray normal close quote period",
     'the X-ray was okay.\n\n"X-ray normal".'),
    ("Thank you for seeing her period", "Thank you for seeing her."),
    ("I have asked her to return period She agreed period", "I have asked her to return. She agreed."),
])
def test_spoken_marks_become_marks(raw, want):
    assert apply(raw, lenient=True, punctuation=True) == want


@pytest.mark.parametrize("text", [
    "Her last period was on the 3rd.",
    "She had a normal period.",
    "Her last menstrual period was in May.",
    "She missed a period.",
    "She missed her period.",
    "Pain since her period started.",
    "Bleeding between periods.",
    "During the observation period he was stable.",
    "The sigmoid colon is thickened.",
    "Family history of colon cancer.",
    "Carcinoma of the colon.",
    "Small bowel and colon were normal.",
    "There was no... ...injury. Cefazolin is documented (see chart) .",   # spacing is not tidied
])
def test_spoken_marks_leave_clinical_nouns(text):
    assert apply(text, lenient=True, punctuation=True) == text


def test_spoken_marks_are_off_by_default():
    raw = "HENT normal period. Throat red comma, no exudate period."
    assert apply(raw) == raw and apply(raw, lenient=True) == raw


def test_lenient_opens_a_quote_the_model_dropped_after_a_break():
    raw = "the mammogram was normal. New paragraph. Routine screening in 2 years. close quote."
    assert apply(raw, lenient=True) == 'the mammogram was normal.\n\n"Routine screening in 2 years".'
    assert apply(raw) != apply(raw, lenient=True)                       # classic behaviour unchanged
    first_line = "Routine screening in 2 years, close quote. New line. Thanks."
    assert '"Routine' not in apply(first_line, lenient=True)           # no break before it: left alone
    both = "Seen. New line. Open quote. Rest. Close quote."
    assert apply(both, lenient=True) == 'Seen.\n"Rest".'


def test_only_dictated_commas_drops_the_ones_the_model_added():
    raw = ("Heart sounds were normal, with no murmurs, period. He takes ramipril comma, metformin 1,000 mg, "
           "and rosuvastatin period. New paragraph. Open quote, rest, close quote period")
    kept = apply(raw, lenient=True, punctuation=True, only_dictated_commas=True)
    assert kept == 'Heart sounds were normal with no murmurs. He takes ramipril, metformin 1,000 mg and rosuvastatin.\n\n"Rest".'
    assert ", with no murmurs" in apply(raw, lenient=True, punctuation=True)          # the default keeps them
    assert apply("stable, today", lenient=True, only_dictated_commas=True) == "stable, today"   # needs spoken punctuation


# ── A letter's greeting and sign-off (natural speech, or a dropped command) ──
@pytest.mark.parametrize("raw, want", [
    ("Dear Dr. Abiodun, Thank you for seeing Ms. Martin. I would be grateful for your advice. "
     "Kind regards, Dr. Owen Gallagher.",
     "Dear Dr. Abiodun,\n\nThank you for seeing Ms. Martin. I would be grateful for your advice.\n\n"
     "Kind regards,\nDr. Owen Gallagher"),
    ("Thank you for seeing him. Thank you, Dr. Priya Raman.", "Thank you for seeing him.\n\nThank you,\nDr. Priya Raman"),
    ("Please call Mrs. Whitfield. Thanks, Sarah.", "Please call Mrs. Whitfield.\n\nThanks,\nSarah"),
    ("To whom it may concern: Mr. Ruiz was seen today.", "To whom it may concern:\n\nMr. Ruiz was seen today."),
    # whoever says layout commands lays the letter out: only the greeting's full stop is mended
    ("Dear Dr. Lee. New paragraph. Seen today. New paragraph. Kind regards, Dr. Ade Bankole.",
     "Dear Dr. Lee,\n\nSeen today.\n\nKind regards, Dr. Ade Bankole."),
    ("Dear Dr. Okafor, Thank you for seeing Ms. Ruiz. New paragraph. Thank you for your help. Kind regards.",
     "Dear Dr. Okafor, Thank you for seeing Ms. Ruiz.\n\nThank you for your help. Kind regards."),
])
def test_letter_greeting_and_sign_off(raw, want):
    assert apply(raw, lenient=True) == want


@pytest.mark.parametrize("text", [
    "Thank you for seeing him.",                          # a body sentence, not a sign-off
    "To be seen in 2 weeks, Dr. Smith will review.",
    "Kind regards to his wife. He is well.",              # no name at the end
    "dear doctor smith, thanks.",                         # not a letter's greeting as written
])
def test_ordinary_text_is_not_laid_out_as_a_letter(text):
    assert apply(text, lenient=True) == text
