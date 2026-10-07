"""Opt-in MedASR formatting experiment; no model, references or medical rules.

Only five exact brace markers observed in the initial real run are interpreted.
Set-off spoken layout and explicit line-start item commands may be mixed with
them. Other markers and ordinary prose remain text for review. This is a
downstream formatting policy, not a complete MedASR command inventory.
"""
import re

KNOWN_MARKERS = ("{newline}", "{open quote}", "{close quote}",
                 "{new paragraph}", "{period}")
_NUMBERS = {word: str(i) for i, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_NATIVE_ITEM = re.compile(
    r"(^|\n)[ \t]*(?i:(?:number[ \t]+)?"
    r"(\d{1,2}|" + "|".join(_NUMBERS) + r"))[ \t]*\{period\}[ \t]*")
_UNKNOWN = re.compile(r"(\{[^{}]+\})")
_SPOKEN_BREAK = re.compile(r"\b(new[ \t]+paragraph|(?:new|next)[ \t]+line)\b", re.I)
_SPOKEN_ITEM = re.compile(
    r"(^|\n)[ \t]*(?P<prefix>number[ \t]+)?"
    r"(?P<number>\d{1,2}|" + "|".join(_NUMBERS) + r")[ \t]+"
    r"(?:period|full[ \t]+stop|dot)\b(?P<separator>[ \t]*[,.;:]+)?[ \t]*", re.I)
_PUNCT = ",.;:!?"


def _outside_braces(text, pattern, replacement):
    """Substitute matches without interpreting any part of an unknown marker."""
    spans = [m.span() for m in _UNKNOWN.finditer(text)]
    return pattern.sub(
        lambda m: m[0] if any(m.start() < end and m.end() > start
                             for start, end in spans) else replacement(m), text)


def _render_spoken_breaks(text):
    """Render layout phrases set off by punctuation or a text/line boundary."""
    spans = [m.span() for m in _UNKNOWN.finditer(text)]
    out, pos = [], 0
    for m in _SPOKEN_BREAK.finditer(text):
        if any(m.start() < end and m.end() > start for start, end in spans):
            continue
        left = text[:m.start()].rstrip(" \t")
        right = text[m.end():].lstrip(" \t")
        # A right separator is explicit. With only a left separator, require
        # the next token to be content rather than a grammatical continuation.
        # This leaves "new line of therapy" and "new paragraph in the note".
        right_boundary = not right or right[0] in _PUNCT + "\n"
        left_boundary = not left or left[-1] in _PUNCT + "\n" or left.endswith("{period}")
        continuation = re.match(r"(?:of|in|for|is|was|with|to|at|on|from|and|or)\b", right, re.I)
        if not (right_boundary or (left_boundary and not continuation)):
            continue
        out.append(text[pos:m.start()].rstrip(" \t").rstrip(",;:"))
        out.append("\n\n" if m[1].lower().endswith("paragraph") else "\n")
        pos = m.end()
        while pos < len(text) and text[pos] in _PUNCT + " \t":
            pos += 1
    out.append(text[pos:])
    return "".join(out)


def render_native(text: str) -> str:
    """Render explicit layout before numbering; never guess damaged commands."""
    text = re.sub(r"[ \t]*\{new paragraph\}[ \t]*", "\n\n", text)
    text = re.sub(r"[ \t]*\{newline\}[ \t]*", "\n", text)
    text = _render_spoken_breaks(text)
    text = _NATIVE_ITEM.sub(
        lambda m: m[1] + _NUMBERS.get(m[2].lower(), m[2]) + ". ", text)
    # A spoken item needs "number" or a punctuation separator after the
    # command. Bare "one period of pain" is prose, even at a line start.
    text = _outside_braces(text, _SPOKEN_ITEM,
        lambda m: (m[1] + _NUMBERS.get(m['number'].lower(), m['number']) + ". "
                   if m['prefix'] or m['separator'] else m[0]))
    text = re.sub(r"[ \t]*\{period\}[ \t]*", ". ", text)
    text = re.sub(r"[ \t]*\{open quote\}[ \t]*", ' "', text)
    text = re.sub(r"[ \t]*\{close quote\}[ \t]*",
                  lambda m: '"' + (' ' if m.end() < len(m.string)
                      and m.string[m.end()] not in '.,;:!?\n' else ''), text)
    # Only trim horizontal whitespace beside the newly rendered layout.
    text = _outside_braces(text, re.compile(r"[ \t]+\n|\n[ \t]+"), lambda m: "\n")
    return text


def postprocess_native(text: str, post) -> str:
    """Bridge before shared spelling rules; protect unknown brace spans from guessing."""
    rendered = render_native(text)
    if post is None:
        return rendered
    return "".join(part if _UNKNOWN.fullmatch(part) else post(part)
                   for part in _UNKNOWN.split(rendered))
