"""
tuning/sets.py — reading sets, and how each kind of speaker dictates them.

A set is a text file of fictional items in their written form, which is the truth:

    ## <id> | <kind> [| <style> | <split>]
    The text as it should finally appear.

<style> is how the speaker dictates (STYLES). <split> is "tune" or "check" and is
fixed before any result is seen. Words in {braces} are said but not written, for
hesitations such as {um}; everything else is both said and written.

spoken_form() turns the written form into what that speaker says. The style
decides WHICH marks and breaks are said aloud; the language decides the WORDS
(English here, other languages from lang_packs). A mark that is not said stays as
plain punctuation, so a reader or a synthetic voice still pauses there.

Moved here from scripts/validation_tool.py so that the setup wizard and the test
scripts share one copy. Guide: docs/testing/README.md.
"""

import re
from pathlib import Path

# What each way of dictating says aloud: which marks, and whether line breaks,
# paragraphs, quotes and list numbers are spoken as commands.
MODES = {
    "every": {"marks": ".,:;?", "layout": True},      # "I say every mark"
    "sentence": {"marks": ".:?", "layout": True},     # "Sometimes": sentence ends, colons, breaks
    "layout": {"marks": "", "layout": True},          # natural sentences plus "new paragraph"
    "natural": {"marks": "", "layout": False},        # just talks
}
# Speaker styles used in set files, and how each dictates. "notes" is a content style
# (quick notes, numbers and units) dictated with sentence marks.
STYLES = {"every": "every", "sentence": "sentence", "layout": "layout", "natural": "natural",
          "notes": "sentence"}
SPLITS = ("tune", "check")
STOP_WORDS = ("period", "full stop")                  # what an English speaker says for "."

_TITLES = ("Mr", "Mrs", "Ms", "Dr", "Miss")
_SAID = {".": "period", ",": "comma", ":": "colon", ";": "semicolon", "?": "question mark"}
_FILLER = re.compile(r"\{([^{}\n]*)\}")


def parse_set(text: str) -> list:
    """[{id, category, style, split, reference, said, spoken}] from the "## id | kind ..." format."""
    items, current = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            fields = [f.strip() for f in line[3:].split("|")] + ["", "", ""]
            ident, kind, style, split = fields[:4]
            if style and style not in STYLES:
                raise ValueError(f"{ident}: unknown style {style!r}")
            if split and split not in SPLITS:
                raise ValueError(f"{ident}: unknown split {split!r}")
            current = {"id": ident, "category": kind or "short", "style": style or None,
                       "split": split or None, "lines": []}
            items.append(current)
        elif current is not None:
            current["lines"].append(line)
    for item in items:
        raw = "\n".join(item.pop("lines")).strip()
        item["said"] = _FILLER.sub(r"\1", raw)
        item["reference"] = raw
        if _FILLER.search(raw):                      # drop the hesitations and the gap they leave
            item["reference"] = "\n".join(re.sub(r"[ \t]{2,}", " ", ln).strip()
                                          for ln in _FILLER.sub("", raw).split("\n"))
        item["spoken"] = spoken_form(item["said"], mode=mode_of(item))
    return items


def mode_of(item: dict) -> str:
    """How the item's speaker dictates; items without a style are read with every mark."""
    return STYLES[item.get("style") or "every"]


def spoken_form(reference: str, shout: bool = False, language: str = "en", mode: str = "every",
                stop: str = "period") -> str:
    """
    The text as it is dictated in `mode` (MODES). With shout=True the dictated words
    are in CAPITALS so they are easy to read out. `language` picks the words (English
    here; others from lang_packs); `stop` is the English word for "." ("period" or
    "full stop").
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    if language != "en":
        return _spoken_form_pack(reference, shout, language, mode)
    said_marks, layout = MODES[mode]["marks"], MODES[mode]["layout"]
    say = (lambda w: w.upper()) if shout else (lambda w: w)
    words = dict(_SAID, **{".": stop})
    text = reference
    text = re.sub(r"(\d)/(\d)", r"\1 over \2", text)
    text = re.sub(r"(\d)%", r"\1 percent", text)
    if layout:
        text = re.sub(r'"([^"\n]*)"', lambda m: f" {say('open quote')} {m.group(1)} {say('close quote')}", text)
        text = re.sub(r"(?m)^(\d{1,2})\. ", lambda m: f"{m.group(1)} {say(stop)} ", text)   # list numbers
    else:
        text = re.sub(r'"([^"\n]*)"', r"\1", text)
    titles = "".join(rf"(?<!\b{t})" for t in _TITLES)                              # "Dr." has no spoken mark
    text = re.sub(titles + r"([.,:;?])(?=\s|$)",                                   # not decimals
                  lambda m: f" {say(words[m.group(1)])}" if m.group(1) in said_marks else m.group(1), text)
    if layout:
        text = re.sub(r"[ \t]*\n[ \t]*\n[ \t]*", f" {say('new paragraph')} ", text)
        text = re.sub(r"[ \t]*\n[ \t]*", f" {say('new line')} ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def _spoken_form_pack(reference: str, shout: bool, language: str, mode: str) -> str:
    import lang_packs
    pack = lang_packs.get(language)
    if pack is None:
        raise SystemExit(f"no language pack for {language!r}")
    said_marks, layout = MODES[mode]["marks"], MODES[mode]["layout"]
    say = (lambda w: w.upper()) if shout else (lambda w: w)
    words, text = pack.say, reference
    text = re.sub(r"(\d)/(\d)", rf"\1 {pack.over[0]} \2", text)
    left, right = (re.escape(q.strip()) for q in pack.quotes)
    text = re.sub(left + r"\s*([^\n]*?)\s*" + right,
                  (lambda m: f" {say(words['open'])} {m.group(1)} {say(words['close'])}") if layout
                  else (lambda m: m.group(1)), text)
    titles = "".join(rf"(?<!\b{t})" for t in pack.titles)
    text = re.sub(r"[ \t]*" + titles + r"([.,:;?])(?=\s|$)",
                  lambda m: f" {say(words[m.group(1)])}" if m.group(1) in said_marks else m.group(0), text)
    if layout:
        text = re.sub(r"[ \t]*\n[ \t]*\n[ \t]*", f" {say(words[chr(10) * 2])} ", text)
        text = re.sub(r"[ \t]*\n[ \t]*", f" {say(words[chr(10)])} ", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def set_language(path: Path) -> str:
    """Language code from the set's file name: validation_set_es_v1.txt -> es (English otherwise)."""
    m = re.search(r"_set_([a-z]{2})_", path.name)
    return m.group(1) if m else "en"


def load_set(path: Path) -> list:
    language = set_language(path)
    items = parse_set(path.read_text(encoding="utf-8"))
    for item in items:
        item["language"] = language
        item["spoken"] = spoken_form(item["said"], language=language, mode=mode_of(item))
    return items
