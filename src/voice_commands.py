"""
voice_commands.py — spoken formatting commands, applied to the final text.

  "new line" / "next line"   -> line break
  "new paragraph"            -> blank line
  "open quote(s)" ... "close quote(s)" / "end quote(s)" / "unquote"  -> "..."
  "<number> period" at the start of a line                          -> "2. "
      e.g. "... new line, 2 period, Xerostomia. Start water-based lubricant."
      -> "\n2. Xerostomia. Start water-based lubricant." Only at a line start, so
      "her last period" or "2 periods of chest pain" mid-sentence are untouched.

Conservative on purpose: a phrase only counts as a command when Whisper set it
off with punctuation on at least one side (or it starts/ends the text), which is
how it transcribes a spoken command ("...2 weeks. New line, follow up..."). In
"start a new line of therapy" nothing separates "new line" from its neighbours,
so it stays text. Pure functions; nothing is logged.

apply(text, lenient=True) (used by the pause-aware pipeline) also accepts a
command the model wrote without any punctuation, which happens when it loses
its punctuation for a stretch ("...chest is clear new paragraph the abdomen is soft..."):
  * "new paragraph" always counts: nobody dictates those two words as text;
    the sentence before it gets its missing full stop;
  * "new line" counts unless its neighbours show it is a noun phrase
    ("a new line of therapy", "the new line on the film", "new line was placed").
Quotes and list numbers are unchanged. The default (lenient=False) is the
original behaviour.
"""

import re

PUNCT = ",.;:!?"
_BREAKS = [(re.compile(r"\bnew\s+paragraph\b", re.I), "\n\n"),
           (re.compile(r"\b(?:new|next)\s+line\b", re.I), "\n")]
_NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
# At a line start: "2 period," / "2. Period." / "two period" / "number 2 period" / "2 full stop",
# and the forms Whisper wrote from real speech: "2 periods," / "2. 2 periods,".
_NUM = r"(?:\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
_LIST_ITEM = re.compile(
    r"(^|\n)[ \t]*(?:number[ \t]+)?(" + _NUM + r")[ \t]*[.,]?[ \t]*(?:" + _NUM + r"[ \t]*)?"
    r"(?:periods?|full[ \t]+stops?|dot)\b[ \t]*[.,:;]*[ \t]*", re.I)
_OPEN = re.compile(r"\bopen\s+quotes?\b", re.I)
_CLOSE = re.compile(r"\b(?:close\s+quotes?|end\s+quotes?|unquote)\b", re.I)


# lenient "new line": words that make it a noun phrase rather than a command.
_LINE_NOT_AFTER = {"a", "an", "the", "this", "that", "another", "any", "no", "one", "her", "his", "their",
                   "our", "its", "each", "every", "second", "third", "of", "with", "for", "and", "or"}
_LINE_NOT_BEFORE = {"of", "on", "in", "at", "to", "for", "was", "is", "has", "had", "were", "are", "placed",
                    "inserted", "started", "sited", "and", "or", "that", "which", "infection", "site"}


def _lenient_ok(text: str, start: int, end: int, paragraph: bool) -> bool:
    """An unpunctuated "new paragraph" / "new line" that still reads as a command."""
    if paragraph:
        return True
    before = re.findall(r"[A-Za-z']+", text[:start])
    after = re.findall(r"[A-Za-z']+", text[end:end + 40])
    return not ((before and before[-1].lower() in _LINE_NOT_AFTER)
                or (after and after[0].lower() in _LINE_NOT_BEFORE))


def _set_off(text: str, start: int, end: int) -> bool:
    """True if text[start:end] has punctuation (or the text edge) on at least one side."""
    left = text[:start].rstrip(" ")
    right = text[end:].lstrip(" ")
    return (not left or left[-1] in PUNCT + "\n") or (not right or right[0] in PUNCT + "\n")


def _replace_commands(text: str, pattern, token: str, lenient: bool = False) -> str:
    """Replace set-off matches with a placeholder token, eating the punctuation around them."""
    out, pos = [], 0
    for m in pattern.finditer(text):
        set_off = _set_off(text, m.start(), m.end())
        if not set_off and not (lenient and token in ("\x03", "\x04")
                                and _lenient_ok(text, m.start(), m.end(), token == "\x03")):
            continue
        left = text[pos:m.start()].rstrip(" ")
        if token in ("\x03", "\x04"):            # line break: keep a full stop, drop , ; :
            left = left.rstrip(",;:")
            if lenient and token == "\x03" and left and left[-1].isalnum():
                left += "."                       # a paragraph ends its sentence
        elif token == "\x02":                     # closer: drop the comma Whisper puts before it
            left = left.rstrip(PUNCT)
        out.append(left)
        out.append(token)
        pos = m.end()
        while pos < len(text) and text[pos] in PUNCT + " ":
            if text[pos] in PUNCT and token == "\x02":
                break                             # "close quote." keeps its full stop
            pos += 1
    out.append(text[pos:])
    return "".join(out)


def apply(text: str, lenient: bool = False) -> str:
    """
    Return `text` with spoken formatting commands turned into formatting.
    lenient=True also accepts "new paragraph" / "new line" written without
    punctuation (see the module docstring).
    """
    if not text:
        return text
    for pattern, br in _BREAKS:
        text = _replace_commands(text, pattern, "\x03" if br == "\n\n" else "\x04", lenient)
    text = _replace_commands(text, _OPEN, "\x01")
    text = _replace_commands(text, _CLOSE, "\x02")
    text = text.replace("\x03", "\n\n").replace("\x04", "\n")
    text = re.sub(r"[ \t]*\x01[ \t]*", ' "', text)   # opening quote: space before, none after
    text = re.sub(r"[ \t]*\x02", '"', text)          # closing quote: hug the last word
    text = re.sub(r'(^|\n) "', r'\1"', text)         # no space before a quote at line start
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip(" \n")
    text = _LIST_ITEM.sub(lambda m: f"{m.group(1)}{_NUMBER_WORDS.get(m.group(2).lower(), m.group(2))}. ", text)
    # Capitalise the first letter of each new line / list item (and of a quote opening
    # it). The very start of the text is left as dictated: it may be pasted mid-sentence.
    text = re.sub(r'(^\d{1,2}\. |\n\d{1,2}\. )("?)([a-z])', lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)
    return re.sub(r'(\n)("?)([a-z])', lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)
