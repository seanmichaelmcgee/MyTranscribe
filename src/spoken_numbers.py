"""
spoken_numbers.py — number words to digits, and units to their abbreviations.

Whisper mostly writes "124 g" by itself; recognisers without that habit
(Parakeet, Canary, MedASR) write "one hundred and twenty four grams". Pure
functions on finished text; part of the opt-in "Extra corrections".

  * A number of two or more words is always converted: "one hundred and twenty
    four" -> 124, "fifty eight" -> 58, "four point two" -> 4.2,
    "two thousand and five" -> 2005.
  * A single number word is converted only in front of something countable in
    a chart ("four months" -> 4 months, "two puffs", "five milligrams"); "one"
    in "no one", "one of the" and "four" in "four-limb" are left alone.
  * After a digit: milligrams -> mg, micrograms -> mcg, millilitres -> mL,
    kilograms -> kg, millimoles -> mmol, millimetres -> mm, centimetres -> cm,
    percent -> %.
"""

import re

_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen".split())}
_TENS = {w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_SCALES = {"hundred": 100, "thousand": 1000}
_NUMBER_WORD = "|".join(list(_UNITS) + list(_TENS) + list(_SCALES))
# A run: number words joined by spaces or hyphens, with "and" and "point" inside.
_RUN = re.compile(r"(?<![\w.-])(?:" + _NUMBER_WORD + r")(?:(?:[ -]| and | point )(?:" + _NUMBER_WORD + r"))*(?![\w-])",
                  re.I)
# What a lone number word may count.
_COUNTED = re.compile(
    r"\s+(?:mg|mcg|g|kg|ml|l|mm|cm|mmol|iu|units?|milligrams?|micrograms?|grams?|kilograms?|millilit(?:re|er)s?|"
    r"lit(?:re|er)s?|millimet(?:re|er)s?|centimet(?:re|er)s?|millimoles?|micromoles?|tablets?|tabs?|capsules?|"
    r"puffs?|drops?|doses?|weeks?|days?|months?|years?|hours?|minutes?|seconds?|percent|pounds?|kilos?|"
    r"packs?|pack[- ]years?|beats|breaths|degrees|times|refills?|litres?|cups?|drinks?|cigarettes?|episodes?|"
    r"blocks?|flights?|falls?|beers?|glasses|colou?rs?|pillows?|stairs|steps|visits?|courses?|nights?|"
    r"agents|medications|drugs|antihypertensives|"
    r"years?[- ]old|weeks?[- ]old|months?[- ]old|days?[- ]old)\b", re.I)
_ABBREVIATE = [(re.compile(r"(?<=\d)\s*(?:" + words + r")\b", re.I), abbr) for words, abbr in (
    (r"milligrams?", " mg"), (r"micrograms?", " mcg"), (r"millilit(?:re|er)s?", " mL"), (r"kilograms?", " kg"),
    (r"millimoles?", " mmol"), (r"micromoles?", " µmol"), (r"millimet(?:re|er)s?", " mm"),
    (r"centimet(?:re|er)s?", " cm"), (r"percent", "%"))]


def _value(words):
    """The number a grammatical run of number words spells, or None."""
    if "point" in words:
        cut = words.index("point")
        whole, digits = _value(words[:cut]), words[cut + 1:]
        if whole is None or not digits or any(d not in _UNITS or _UNITS[d] > 9 for d in digits):
            return None
        return f"{whole}." + "".join(str(_UNITS[d]) for d in digits)
    total = current = 0
    last = None                                   # "units" | "tens" | "scale"
    for i, w in enumerate(words):
        if w == "and":
            if last != "scale" or i == len(words) - 1:
                return None
            continue
        if w in _UNITS:
            if last == "units" or (last == "tens" and _UNITS[w] > 9):
                return None
            current, last = current + _UNITS[w], "units"
        elif w in _TENS:
            if last in ("units", "tens"):
                return None
            current, last = current + _TENS[w], "tens"
        elif w == "hundred":
            if last != "units" or not 0 < current < 10:
                return None
            current, last = current * 100, "scale"
        else:                                     # thousand
            if current == 0 or last == "scale" and current % 100 == 0 and current >= 1000:
                return None
            total, current, last = total + current * 1000, 0, "scale"
    return str(total + current)


def numbers_to_digits(text: str) -> str:
    def convert(m):
        words = re.split(r"[ -]", m.group(0).lower())
        if len(words) == 1:
            if not _COUNTED.match(text, m.end()):
                return m.group(0)
            if words[0] == "one" and re.match(r"\s+times?\b", text[m.end():], re.I):
                return m.group(0)
        elif "-" in m.group(0) and len(words) == 2 and words[0] in _UNITS:
            return m.group(0)                     # "four-five days", "one-two": not a number
        value = _value(words)
        if (value is None and 2 <= len(words) <= 3 and words[0] in _UNITS and 0 < _UNITS[words[0]] < 10
                and words[1] in _TENS and (re.match(r"\s+over\b", text[m.end():], re.I)
                                           or re.search(r"\bover\s+$", text[:m.start()], re.I))):
            rest = _value(words[1:])              # a blood pressure said as "one thirty eight over ..."
            value = None if rest is None else str(100 * _UNITS[words[0]] + int(rest))
        return m.group(0) if value is None else value

    return _RUN.sub(convert, text)


def abbreviate_units(text: str) -> str:
    for pattern, abbr in _ABBREVIATE:
        text = pattern.sub(abbr, text)
    return text


def normalise(text: str) -> str:
    """Number words -> digits, then units after a digit -> abbreviations."""
    return abbreviate_units(numbers_to_digits(text))
