"""
live_insert.py: what "Type into my document while I dictate" types next.

Typing each finished piece formatted on its own loses whatever depends on the
next piece: a spoken "new paragraph" at the end of a piece has nothing after it
yet and falls off, a hesitation "..." before the next word cannot be cleaned
up, and a full stop the model wrote at the end of a piece becomes a comma when
the next piece starts with a spoken "comma". So the whole transcript so far is
formatted every time (exactly as the copy at Stop is), and only what is new is
typed. While dictation goes on, the trailing marks (a break, "...", the last
punctuation mark) are held back until the next piece shows what follows them.

Text already typed cannot be taken back. If formatting the longer transcript
changed something that was typed (rare: a correction that needed later words),
typing carries on after the same number of words, so nothing is typed twice.

Pure functions; nothing is logged.
"""

import re

_HELD_TAIL = re.compile(r"(?:\s|\.\.\.|…|[.,;:!?])+$")
_WORD = re.compile(r"\S+")


def stable(full: str) -> str:
    """The part of a transcript that will not change when more speech follows."""
    return _HELD_TAIL.sub("", full)


def next_text(typed: str, full: str, final: bool = False) -> str:
    """
    Text to type after `typed` (everything typed so far) so the document follows
    `full`, the whole transcript formatted as it would be copied. With final=False
    a trailing break or "..." is held back.
    """
    target = full if final else stable(full)
    if target.startswith(typed):
        return target[len(typed):]
    words = len(typed.split())                   # diverged: continue after as many words as were typed
    if words == 0:
        return target
    found = list(_WORD.finditer(target))
    if words >= len(found):
        return ""
    return target[found[words - 1].end():]
