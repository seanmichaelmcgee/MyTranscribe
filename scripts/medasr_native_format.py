"""Opt-in MedASR formatting experiment; no model, references or medical rules.

Only five exact brace markers observed in the initial real run are interpreted.
Other markers and ordinary spoken prose remain text for review. Google describes
brace forms as explicitly spoken commands, distinct from inferred punctuation:
https://discuss.ai.google.dev/t/116107/4
This is a downstream formatting policy, not a complete MedASR command inventory.
"""
import re

KNOWN_MARKERS = ("{newline}", "{open quote}", "{close quote}",
                 "{new paragraph}", "{period}")
_NUMBERS = {word: str(i) for i, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_NATIVE_ITEM = re.compile(
    r"(^|\{newline\}|\{new paragraph\})[ \t]*(?:number[ \t]+)?"
    r"(\d{1,2}|(?i:" + "|".join(_NUMBERS) + r"))[ \t]*\{period\}[ \t]*")
_UNKNOWN = re.compile(r"(\{[^{}\n]+\})")


def render_native(text: str) -> str:
    """Render known exact markers, including numbered items at explicit line starts."""
    text = _NATIVE_ITEM.sub(
        lambda m: m[1] + _NUMBERS.get(m[2].lower(), m[2]) + ". ", text)
    text = re.sub(r"[ \t]*\{new paragraph\}[ \t]*", "\n\n", text)
    text = re.sub(r"[ \t]*\{newline\}[ \t]*", "\n", text)
    text = re.sub(r"[ \t]*\{period\}[ \t]*", ". ", text)
    text = re.sub(r"[ \t]*\{open quote\}[ \t]*", ' "', text)
    text = re.sub(r"[ \t]*\{close quote\}[ \t]*",
                  lambda m: '"' + (' ' if m.end() < len(m.string)
                      and m.string[m.end()] not in '.,;:!?\n' else ''), text)
    # Only trim horizontal whitespace beside the newly rendered layout.
    text = re.sub(r"[ \t]+\n|\n[ \t]+", "\n", text)
    return text


def postprocess_native(text: str, post) -> str:
    """Bridge before shared spelling rules; protect unknown brace spans from guessing."""
    rendered = render_native(text)
    if post is None:
        return rendered
    return "".join(part if _UNKNOWN.fullmatch(part) else post(part)
                   for part in _UNKNOWN.split(rendered))
