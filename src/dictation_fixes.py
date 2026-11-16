"""
dictation_fixes.py — numbers clinicians read out digit by digit.

Part of the opt-in "Extra corrections" (English). Found on Modulate's Synthetic
Medical Dictation development notes, where the app never wrote a date of birth
in one piece and broke one chart number in five.

  * "Date of birth 0-8-1-2-19-84" / "08121984" -> "Date of birth 08/12/1984"
    (the digits in the order they were said; no day/month guessing).
  * "Chart number 8, 8-0-7-2-9." -> "Chart number 880729."

Tried and not kept: using the letters of a spelled-out name ("Thibodaux,
T H I B O D E A U X") to correct the name. On the same notes the model's
letters were wrong more often than its word (a letter dropped, or the next
word swallowed: "LOMBARDIHR"), and the repair lost 25 names for 4 gained.

Pure functions; nothing is logged.
"""

import re

_DOB = re.compile(r"\b([Dd]ate,? of birth|DOB)\b([\s,:.]*)((?:\d[\d \t,\-./]*){6,}\d)")
_CHART = re.compile(r"\b([Cc]hart,? number|[Mm]edical record number|MRN)\b([\s,:.]*)(\d(?:[ \t,\-]*\d){3,11})(?=([.,]?)(\s|$))")


def join_date_of_birth(text: str) -> str:
    def fix(m):
        digits = re.sub(r"\D", "", m.group(3))
        if len(digits) != 8 or not ("1900" <= digits[4:] <= "2099") or int(digits[:2]) > 31 or int(digits[2:4]) > 31 \
                or "00" in (digits[:2], digits[2:4]):
            return m.group(0)
        return f"{m.group(1)}{m.group(2) or ' '}{digits[:2]}/{digits[2:4]}/{digits[4:]}"
    return _DOB.sub(fix, text)


def join_chart_number(text: str) -> str:
    def fix(m):
        digits = re.sub(r"\D", "", m.group(3))
        return f"{m.group(1)}{m.group(2) or ' '}{digits}"
    return _CHART.sub(fix, text)


def apply(text: str) -> str:
    return join_chart_number(join_date_of_birth(text))
