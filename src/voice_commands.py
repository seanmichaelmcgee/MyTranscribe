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

apply(text, punctuation=True) (Options -> "Spoken punctuation", off by default)
also converts dictated marks, for people who say them:
  "period" / "full stop" -> .    "comma" -> ,    "colon" -> :    "semicolon" -> ;
  "question mark" -> ?    "exclamation mark|point" -> !    "hyphen" -> joins the
  two words    "open paren(thesis)|bracket" ... "close paren(thesis)|bracket" -> ( )
The dictated mark replaces whatever the model put after the word ("stable
period. He" -> "stable. He"; "Plan colon, rest" -> "Plan: rest"). "period" and
"colon" are also ordinary clinical words, so they stay text when the words
around them make them a noun: "her last period", "a normal period", "period
of observation", "the sigmoid colon", "colon cancer". That guard is a word
list, not understanding: with the option on, an unusual noun use can still be
converted, which is why it is a choice.
"""

import re

PUNCT = ",.;:!?"
# A few words of dictation with the commands spoken, appended to Whisper's style prompt
# when Spoken punctuation is on. Whisper treats its prompt as what came before; with this
# example it keeps a spoken "open quote" or "new paragraph" instead of dropping it as an
# aside (fictional validation set: commands 39/40 -> 40/40; owner's development
# recordings: 52/58 -> 54/58, no change for the worse elsewhere).
DICTATION_EXAMPLE = ("The chest is clear, period. New paragraph. No fever, comma, no cough, period. New line. "
                     "Open quote, rest, close quote, period.")
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
    edge = PUNCT + "\n\x03\x04"                    # a line or paragraph break just made also sets it off
    return (not left or left[-1] in edge) or (not right or right[0] in edge)


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


# ── Spoken punctuation marks ─────────────────────────────────────────────────
_MARKS = {"period": ".", "full stop": ".", "comma": ",", "colon": ":", "semicolon": ";", "semi-colon": ";",
          "question mark": "?", "exclamation mark": "!", "exclamation point": "!"}
_MARK = re.compile(r"(?<![\w-])(" + "|".join(k.replace(" ", r"[ \t]+") for k in sorted(_MARKS, key=len, reverse=True))
                   + r")(?![\w-])", re.I)
_DETERMINERS = {"a", "an", "the", "this", "that", "her", "his", "my", "your", "their", "our", "each", "every",
                "per", "any", "no", "one", "same", "which", "what"}
# "period" as a noun: directly after a determiner, after one of these adjectives
# with a determiner or another of them just before ("a normal period", "her last
# menstrual period"), or before one of the followers ("period of observation").
_PERIOD_ADJ = {"last", "first", "next", "previous", "menstrual", "missed", "late", "heavy", "light", "irregular",
               "regular", "normal", "time", "long", "short", "brief", "prolonged", "extended", "incubation",
               "recovery", "observation", "trial", "refractory", "latent", "postoperative", "perioperative",
               "postpartum", "neonatal", "washout", "waiting", "follow-up", "study", "treatment", "initial",
               "whole", "entire", "second", "third", "monthly", "painful"}
# Words after which "her" is a person, not the owner of a period.
_HER_IS_OBJECT = {"seeing", "see", "saw", "seen", "for", "to", "with", "told", "tell", "advised", "advise", "called",
                  "call", "gave", "give", "asked", "ask", "about", "examined", "reviewed", "reassured", "referred",
                  "refer", "thank", "thanked", "help", "helping", "assess", "assessing", "from", "by", "let",
                  "inform", "informed", "treat", "treated", "met", "discharged", "discharge", "following",
                  "assessed", "review", "contact", "contacted", "phoned", "book", "booked", "send", "sent"}
_PERIOD_NEXT = {"of", "was", "is", "has", "had", "pain", "pains", "cramps", "lasted", "started", "due",
                "when", "during", "between"}
_COLON_PREV = _DETERMINERS | {"of", "sigmoid", "ascending", "descending", "transverse", "proximal", "distal", "left",
                              "right", "entire", "whole", "in", "to", "and", "or", "redundant", "irritable",
                              "spastic", "toxic", "normal", "large", "dilated", "remaining", "throughout"}
_COLON_NEXT = {"cancer", "carcinoma", "polyp", "polyps", "resection", "was", "is", "wall", "mass", "biopsy",
               "and", "or", "showed", "appears", "appeared", "tumour", "tumor", "lesion", "adenocarcinoma",
               "screening", "with", "to", "at", "has", "had", "were", "are", "cleansing", "prep", "preparation"}
_OPEN_PAREN = re.compile(r"[ \t]*[,;:]?[ \t]*\b(?:open|left)[ \t]+(?:paren(?:thesis|theses)?|brackets?)\b[ \t]*[.,;:]*[ \t]*", re.I)
_CLOSE_PAREN = re.compile(r"[ \t]*[.,;:]*[ \t]*\b(?:close|right|end)[ \t]+(?:paren(?:thesis|theses)?|brackets?)\b",
                          re.I)
_HYPHEN = re.compile(r"(?<=\w)[ \t]*,?[ \t]+hyphen\b[ \t]*[.,]?[ \t]+(?=\w)", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
_LINE_START = "\n\x03\x04"                       # real breaks and apply()'s break placeholders
# "2 period" opening a line is a list number; _LIST_ITEM converts it.
_LIST_HEAD = re.compile(r"(?:^|[" + _LINE_START + r"])[ \t]*(?:number[ \t]+)?" + _NUM + r"[ \t]*[.,]?[ \t]*(?:"
                        + _NUM + r"[ \t]*)?$", re.I)


def _is_noun(word: str, before: str, after: str) -> bool:
    """True when "period" / "colon" at this place reads as an ordinary word."""
    if word == "period" and _LIST_HEAD.search(before):
        return True
    before = re.split(r"[" + re.escape(PUNCT) + _LINE_START + r"]", before)[-1]   # same clause only
    prev = [w.lower() for w in _WORD.findall(before[-40:])][-2:]
    nxt = _WORD.match(after.lstrip(" \t"))
    nxt = nxt.group(0).lower() if nxt else ""
    if word == "period":
        if len(prev) > 1 and prev[-1] == "her" and prev[-2] in _HER_IS_OBJECT:
            return False                              # "thank you for seeing her period": her = the patient
        return nxt in _PERIOD_NEXT or (bool(prev) and (
            prev[-1] in _DETERMINERS
            or (prev[-1] in _PERIOD_ADJ and len(prev) > 1 and prev[-2] in _DETERMINERS | _PERIOD_ADJ)))
    if word == "colon":
        return nxt in _COLON_NEXT or (bool(prev) and prev[-1] in _COLON_PREV)
    return False


def spoken_marks(text: str) -> str:
    """Dictated punctuation marks -> the marks (see the module docstring)."""
    text = _CLOSE_PAREN.sub(")", _OPEN_PAREN.sub(" (", text))
    text = _HYPHEN.sub("-", text)
    out, pos = [], 0
    for m in _MARK.finditer(text):
        word = re.sub(r"\s+", " ", m.group(1).lower())
        if _is_noun(word, text[:m.start()], text[m.end():]):
            continue
        left = text[pos:m.start()].rstrip(" \t")
        while left and left[-1] in PUNCT:             # the dictated mark replaces the model's own
            left = left[:-1].rstrip(" \t")
        out.append(left)
        written = "".join(out)
        if written and written[-1] not in PUNCT + _LINE_START + "(":
            out.append(_MARKS[word])                  # nothing to attach to at a text or line start
        pos = m.end()
        while pos < len(text) and text[pos] in PUNCT + " \t":
            pos += 1
        if pos < len(text) and text[pos] not in _LINE_START and written and written[-1] not in _LINE_START:
            out.append(" ")
        if pos < len(text) and _MARKS[word] in ".?!" and text[pos].islower():
            out.append(text[pos].upper())
            pos += 1
    out.append(text[pos:])
    return "".join(out)


def _open_missing_quotes(text: str) -> str:
    """
    The model sometimes leaves out a spoken "open quote" but keeps the "close
    quote". When a line that follows a dictated break has a closing quote and
    no opening one, the quote is taken to start with the line ("new paragraph,
    open quote, X-ray normal, close quote"). The first line is left alone:
    there is no telling where its quote began.
    """
    parts = re.split(r"([\x03\x04])", text)
    for i in range(2, len(parts), 2):
        line = parts[i]
        close = line.find("\x02")
        if close != -1 and "\x01" not in line[:close]:
            parts[i] = "\x01" + line.lstrip(" ")
    return "".join(parts)


def apply(text: str, lenient: bool = False, punctuation: bool = False) -> str:
    """
    Return `text` with spoken formatting commands turned into formatting.
    lenient=True also accepts "new paragraph" / "new line" written without
    punctuation; punctuation=True also converts dictated marks ("period",
    "comma", ...). See the module docstring.
    """
    if not text:
        return text
    for pattern, br in _BREAKS:
        text = _replace_commands(text, pattern, "\x03" if br == "\n\n" else "\x04", lenient)
    if punctuation:
        text = spoken_marks(text)
    text = _replace_commands(text, _OPEN, "\x01")
    text = _replace_commands(text, _CLOSE, "\x02")
    if lenient:
        text = _open_missing_quotes(text)
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
