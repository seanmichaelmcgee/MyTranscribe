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
