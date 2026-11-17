"""
lang_commands.py — spoken formatting for languages other than English.

Driven entirely by a lang_packs.LanguagePack. The behaviour mirrors the English
code in voice_commands.py, in its lenient form (a command counts with or
without punctuation around it, because there are no recordings yet to tell how
the model writes them in each language):

  * paragraph and line phrases become breaks; the sentence before a paragraph
    gets its full stop;
  * quote and parenthesis phrases become the marks;
  * with punctuation=True, mark words become marks, unless the pack's guard
    says the word is an ordinary noun there ("en coma", "un point de suture");
    the dictated mark replaces whatever the model wrote after the word;
  * readings: "140 sobre 90" -> 140/90, "124 gramos por litro" -> 124 g/L.

Pure functions; nothing is logged.
"""

import re

from lang_packs import LanguagePack

PUNCT = ",.;:!?"
_OPENERS = "¿¡"
_BREAK = {"paragraph": "\x03", "line": "\x04"}
_WORD = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
_NUMBER = r"\d+(?:[.,]\d+)?"


def _phrase(text: str) -> str:
    """Regex for a phrase: flexible spaces, apostrophe variants."""
    return r"[ \t]+".join(re.escape(part).replace("'", "['’]").replace("’", "['’]") for part in text.split())


def _any(phrases, loose: bool = False) -> "re.Pattern":
    """One pattern for the phrases; loose=True also accepts a comma between a phrase's words ("nuevo, párrafo")."""
    body = "|".join(_phrase(p) for p in sorted(phrases, key=len, reverse=True))
    if loose:
        body = body.replace(r"[ 	]+", r"[ 	]*,?[ 	]+")
    return re.compile(r"(?<![\w-])(" + body + r")(?![\w-])", re.I | re.UNICODE)


def _replace(text: str, pattern, token: str, full_stop: bool = False) -> str:
    """Replace each match with `token`, eating the punctuation and spaces around it."""
    out, pos = [], 0
    for m in pattern.finditer(text):
        left = text[pos:m.start()].rstrip(" \t")
        if token in "\x03\x04":
            left = left.rstrip(",;:")
            if full_stop and left and left[-1] not in PUNCT + "\x03\x04\n" and left[-1].isalnum():
                left += "."
        elif token == "\x02":
            left = left.rstrip(PUNCT + " \t")
        out += [left, token]
        pos = m.end()
        while pos < len(text) and text[pos] in PUNCT + " \t":
            if text[pos] in PUNCT and token in "\x02\x06":
                break                                # a closing quote or bracket keeps the mark after it
            pos += 1
    out.append(text[pos:])
    return "".join(out)


def _is_noun(pack: LanguagePack, phrase: str, before: str, after: str) -> bool:
    guard = pack.guards.get(phrase)
    if guard is None:
        return False
    clause = re.split(r"[" + re.escape(PUNCT) + "\n\x03\x04]", before)[-1]
    prev = re.findall(r"[\w'’-]+", clause[-40:], re.UNICODE)      # the word right before; a number is not one
    nxt = _WORD.match(after.lstrip(" \t"))
    return bool(prev and prev[-1].lower() in guard.prev) or bool(nxt and nxt.group(0).lower() in guard.next)


def _marks(text: str, pack: LanguagePack) -> str:
    pattern = _any(pack.marks)
    lookup = {re.sub(r"\s+", " ", k.lower()).replace("’", "'"): v for k, v in pack.marks.items()}
    out, pos = [], 0
    for m in pattern.finditer(text):
        phrase = re.sub(r"\s+", " ", m.group(1).lower()).replace("’", "'")
        if _is_noun(pack, phrase, text[:m.start()], text[m.end():]):
            continue
        mark = lookup[phrase]
        left = text[pos:m.start()].rstrip(" \t")
        if mark in _OPENERS:                          # ¿ ¡ open a sentence: space before, none after
            out.append(left + (" " if left and left[-1] not in "\n\x03\x04" else "") + mark)
            pos = m.end()
            while pos < len(text) and text[pos] in PUNCT + " \t":
                pos += 1
            continue
        if mark == "-":                               # joins the two words
            out.append(left.rstrip(PUNCT + " \t") + "-")
            pos = m.end()
            while pos < len(text) and text[pos] in PUNCT + " \t":
                pos += 1
            continue
        while left and left[-1] in PUNCT:             # the dictated mark replaces the model's own
            left = left[:-1].rstrip(" \t")
        after = text[m.end():].lstrip(" \t")
        if mark == "," and left[-1:].isdigit() and after[:1].isdigit():
            out.append(left + ",")                    # a decimal: "5 coma 4" -> 5,4
            pos = len(text) - len(after)
            continue
        out.append(left)
        written = "".join(out)
        if written and written[-1] not in PUNCT + "\n\x03\x04(" + _OPENERS:
            out.append((" " if mark in pack.space_before else "") + mark)
        pos = m.end()
        while pos < len(text) and text[pos] in PUNCT + " \t":
            pos += 1
        if pos < len(text) and text[pos] not in "\n\x03\x04" and written and written[-1] not in "\n\x03\x04":
            out.append(" ")
        if pos < len(text) and mark in ".?!" and text[pos].islower():
            out.append(text[pos].upper())
            pos += 1
    out.append(text[pos:])
    return "".join(out)


_DESCENDING_PAIR = re.compile(r"(?<![\w/.,-])(\d{2,3})-(\d{2,3})(?![\w/-]|[.,]\d)")


def format_readings(text: str, pack: LanguagePack) -> str:
    """Blood pressures and unit ratios written the chart way; units after a digit abbreviated."""
    if pack.number_words and pack.counted:                # "cuatro años" -> 4 años, as the model usually writes it
        text = re.sub(r"(?<![\w-])(" + "|".join(pack.number_words) + r")(?=[ \t]+(?:" + "|".join(pack.counted)
                      + r")(?![\w-]))", lambda m: pack.number_words[m.group(1).lower()], text, flags=re.I)
    for word in pack.over:
        text = re.sub(r"(?<![\w./])(\d{2,3})[ \t]+" + _phrase(word) + r"[ \t]+(\d{2,3})(?!\w|[./]\d)", r"\1/\2",
                      text, flags=re.I)
    # "155-95", "875-125": a larger number before a smaller one is a pressure or a fixed
    # combination, written with a slash; a range ("4-6", "10-15") goes upwards and keeps its hyphen.
    text = _DESCENDING_PAIR.sub(lambda m: f"{m.group(1)}/{m.group(2)}" if int(m.group(1)) > int(m.group(2))
                                else m.group(0), text)
    for spoken, abbr in sorted(pack.units.items(), key=lambda kv: -len(kv[0])):
        sep = "" if abbr.strip() == "%" and not abbr.startswith(" ") else " "
        text = re.sub(r"(?<=\d)[ \t]*" + _phrase(spoken) + r"(?![\w-])", sep + abbr.strip(), text, flags=re.I)
    if pack.per and pack.per_units:
        units = "|".join(sorted({re.escape(v) for v in pack.units.values() if v.strip() != "%"}, key=len, reverse=True))
        dens = "|".join(_phrase(k) for k in sorted(pack.per_units, key=len, reverse=True))
        per = "|".join(_phrase(p) for p in pack.per)
        lookup = {k.lower(): v for k, v in pack.per_units.items()}
        text = re.sub(r"(" + _NUMBER + r") (" + units + r")[ \t]+(?:" + per + r")[ \t]+(" + dens + r")s?(?![\w-])",
                      lambda m: f"{m.group(1)} {m.group(2)}/{lookup[m.group(3).lower()]}", text, flags=re.I)
    return text


_correctors = {}


def corrector_for(pack: LanguagePack):
    """
    The spelling corrector for the language's medical term list, or None when
    the pack has no list, the optional packages are missing, or there is no
    word-frequency data to tell a real word from a misspelling (Swahili).
    """
    if pack.code not in _correctors:
        corrector = None
        if pack.vocab_file:
            from pathlib import Path
            from vocab_correct import make_corrector
            path = Path(__file__).parent / "vocab" / pack.vocab_file
            terms = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                     if line.strip() and not line.startswith("#")]
            corrector = make_corrector(terms, language=pack.code)
        _correctors[pack.code] = corrector
    return _correctors[pack.code]


def prompt_for(pack: LanguagePack, punctuation: bool) -> str:
    """Whisper's style prompt for the language; with dictated punctuation, an example of it comes last."""
    if punctuation and pack.dictation_prompt:
        return (pack.prompt + " " + pack.dictation_prompt).strip()
    return pack.prompt


def clean(text: str, pack: LanguagePack) -> str:
    """Drop invented closing lines and apply the pack's one-reading fixes ("incomprimé" -> "1 comprimé")."""
    for pattern in pack.phantoms:
        text = re.sub(r"[ \t]*" + pattern + r"[ \t.!]*$", "", text, flags=re.I)
    for pattern, replacement in pack.fixes:
        text = re.sub(pattern, replacement, text)
    return text


def apply(text: str, pack: LanguagePack, punctuation: bool = False) -> str:
    """Spoken formatting commands (and, with punctuation=True, dictated marks) -> formatting."""
    if not text:
        return text
    text = clean(text, pack)
    if pack.paragraph:
        text = _replace(text, _any(pack.paragraph, loose=True), "\x03", full_stop=True)   # a paragraph ends its sentence
    if pack.line:
        text = _replace(text, _any(pack.line, loose=True), "\x04")
    if punctuation and pack.marks:
        text = _marks(text, pack)
    if pack.open_quote:
        text = _replace(text, _any(pack.open_quote, loose=True), "\x01")
    if pack.close_quote:
        text = _replace(text, _any(pack.close_quote, loose=True), "\x02")
    if pack.open_paren:
        text = _replace(text, _any(pack.open_paren, loose=True), "\x05")
    if pack.close_paren:
        text = _replace(text, _any(pack.close_paren, loose=True), "\x06")
    text = text.replace("\x03", "\n\n").replace("\x04", "\n")
    text = re.sub(r"[ \t]*\x01[ \t]*", " " + pack.quotes[0], text)
    text = re.sub(r"[ \t]*\x02", pack.quotes[1], text)
    text = re.sub(r"[ \t]*\x05[ \t]*", " (", text)
    text = re.sub(r"[ \t]*\x06", ")", text)
    text = re.sub(r"(^|\n)[ \t]+", r"\1", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip(" \n")
    # A sentence end glued to the next sentence ("mazingira.Salama", where two pieces of audio met).
    text = re.sub(r"(?<=[^\W\d_]{3})([.?!])(?=[A-ZÀ-ÖØ-Þ][^\W\d_])", r"\1 ", text, flags=re.UNICODE)
    # Capitalise the first letter of each new line (after an opening quote, bracket or ¿ ¡ too).
    return re.sub(r"(\n)([\"«(¿¡ ]*)([^\W\d_])", lambda m: m.group(1) + m.group(2) + m.group(3).upper(), text,
                  flags=re.UNICODE)
