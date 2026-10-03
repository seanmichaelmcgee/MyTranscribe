"""
voice_commands.py — spoken formatting commands, applied to the final text.

  "new line" / "next line"   -> line break
  "new paragraph"            -> blank line
  "open quote(s)" ... "close quote(s)" / "end quote(s)" / "unquote"  -> "..."

Conservative on purpose: a phrase only counts as a command when Whisper set it
off with punctuation on at least one side (or it starts/ends the text), which is
how it transcribes a spoken command ("...2 weeks. New line, follow up..."). In
"start a new line of therapy" nothing separates "new line" from its neighbours,
so it stays text. Pure functions; nothing is logged.
"""

import re

PUNCT = ",.;:!?"
_BREAKS = [(re.compile(r"\bnew\s+paragraph\b", re.I), "\n\n"),
           (re.compile(r"\b(?:new|next)\s+line\b", re.I), "\n")]
_OPEN = re.compile(r"\bopen\s+quotes?\b", re.I)
_CLOSE = re.compile(r"\b(?:close\s+quotes?|end\s+quotes?|unquote)\b", re.I)


def _set_off(text: str, start: int, end: int) -> bool:
    """True if text[start:end] has punctuation (or the text edge) on at least one side."""
    left = text[:start].rstrip(" ")
    right = text[end:].lstrip(" ")
    return (not left or left[-1] in PUNCT + "\n") or (not right or right[0] in PUNCT + "\n")


def _replace_commands(text: str, pattern, token: str) -> str:
    """Replace set-off matches with a placeholder token, eating the punctuation around them."""
    out, pos = [], 0
    for m in pattern.finditer(text):
        if not _set_off(text, m.start(), m.end()):
            continue
        left = text[pos:m.start()].rstrip(" ")
        if token in ("\x03", "\x04"):            # line break: keep a full stop, drop , ; :
            left = left.rstrip(",;:")
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


def apply(text: str) -> str:
    """Return `text` with spoken formatting commands turned into formatting."""
    if not text:
        return text
    for pattern, br in _BREAKS:
        text = _replace_commands(text, pattern, "\x03" if br == "\n\n" else "\x04")
    text = _replace_commands(text, _OPEN, "\x01")
    text = _replace_commands(text, _CLOSE, "\x02")
    text = text.replace("\x03", "\n\n").replace("\x04", "\n")
    text = re.sub(r"[ \t]*\x01[ \t]*", ' "', text)   # opening quote: space before, none after
    text = re.sub(r"[ \t]*\x02", '"', text)          # closing quote: hug the last word
    text = re.sub(r'(^|\n) "', r'\1"', text)         # no space before a quote at line start
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip(" \n")
    # Capitalise the first letter of each new line (and of a quote opening it). The very
    # start of the text is left as dictated: it may be pasted mid-sentence.
    return re.sub(r'(\n)("?)([a-z])', lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text)
