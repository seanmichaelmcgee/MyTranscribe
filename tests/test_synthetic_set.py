"""
The synthetic voice set: the rules every language's set is written to.

Plan and reasons: docs/testing/SYNTHETIC_VOICES.md. A new language adds its file
(validation/synthetic_set_<lang>_v1.txt) and an entry in FEATURES; everything else
here applies to it unchanged.
"""

import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

import lang_packs
import text_fixes
import voice_commands
from tuning import sets

ROOT = Path(__file__).resolve().parent.parent
SETS = sorted((ROOT / "validation").glob("synthetic_set_*_v1.txt"))
EVALUATION_SETS = sorted((ROOT / "validation").glob("validation_set_*.txt"))
PER_STYLE, TUNE, CHECK = 8, 5, 3
WORDS_PER_STYLE = (450, 800)            # about 4 to 6 minutes of speech per style

# What each feature looks like in each language. "dose" and "negation" must be in every item;
# the others must appear in at least MINIMUM items of the whole set.
FEATURES = {
    "en": {
        "dose": r"\b\d+(?:\.\d+)?(?:/\d+)? ?(?:mg|mcg|g|units|drops|puffs)\b",
        "negation": r"\b(?:no|not|none|never|without|nor|cannot)\b",
        "salutation": r"(?m)^Dear Dr\. ",
        "sign_off": r"(?m)^(?:Kind regards|Yours sincerely|Thank you),$",
        "heading": r"(?m)^[A-Z][A-Za-z ]{1,30}:",
        "list": r"(?m)^\d{1,2}\. ",
        "reading": r"\b\d{2,3}/\d{2,3}\b",
        "percent": r"\d%",
        "question": r"\?",
        "quote": r'"',
        "semicolon": r";",
        "self_correction": r"\bsorry\b",
    },
}
MINIMUM = {"salutation": 12, "sign_off": 12, "heading": 6, "list": 3, "reading": 6, "percent": 4,
           "question": 4, "quote": 1, "semicolon": 2, "self_correction": 2}
COMMAND_WORDS = re.compile(r"\b(?:new line|new paragraph|open quote|close quote|full stop)\b", re.I)

# Items that hit a known gap in the app's rules when the words come with no punctuation at
# all (the lenient path). With Whisper's usual punctuation both convert correctly. Kept in
# the set because clinicians say them; xfail(strict) flags the day the rule is improved.
KNOWN_GAPS = {
    "e03": "a quote in mid-sentence is converted only when punctuation sets it off",
    "s04": "'new line' followed by 'On examination' is read as a noun phrase ('the new line on ...')",
}


def load(path):
    return sets.load_set(path)


def words(text):
    return re.findall(r"[^\W_]+(?:['’\-./][^\W_]+)*", text)


def back_to_text(spoken, language):
    """What the app's own rules make of the dictated words, for that language."""
    if language == "en":
        return voice_commands.apply(text_fixes.format_readings(spoken), lenient=True, punctuation=True)
    import lang_commands
    pack = lang_packs.get(language)
    return lang_commands.apply(lang_commands.format_readings(spoken, pack), pack, punctuation=True)


def unmarked(text):
    """Text without , ; : . ? so that only words and layout are compared."""
    return re.sub(r"[,;:.?]", "", text)


def cases():
    out = []
    for path in SETS:
        for it in load(path):
            if it["style"] == "natural":
                continue
            marks = [pytest.mark.xfail(strict=True, reason=KNOWN_GAPS[it["id"]])] if it["id"] in KNOWN_GAPS else []
            out.append(pytest.param(path, it["id"], id=f"{path.stem}-{it['id']}", marks=marks))
    return out


def test_every_set_has_its_language_features():
    assert SETS, "no synthetic set found"
    for path in SETS:
        assert sets.set_language(path) in FEATURES, path.name


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.stem)
def test_each_style_has_its_items_split_in_advance(path):
    items = load(path)
    assert len({it["id"] for it in items}) == len(items)
    by_style = defaultdict(list)
    for it in items:
        assert it["style"] in sets.STYLES and it["split"] in sets.SPLITS, it["id"]
        by_style[it["style"]].append(it)
    assert set(by_style) == set(sets.STYLES)
    for style, group in by_style.items():
        splits = Counter(it["split"] for it in group)
        assert (len(group), splits["tune"], splits["check"]) == (PER_STYLE, TUNE, CHECK), style
        kinds = {it["category"] for it in group}
        checked = {it["category"] for it in group if it["split"] == "check"}
        assert len(checked) >= min(2, len(kinds)), f"{style}: check items should mix kinds"
        n = sum(len(words(it["reference"])) for it in group)
        assert WORDS_PER_STYLE[0] <= n <= WORDS_PER_STYLE[1], f"{style}: {n} words"


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.stem)
def test_every_item_has_a_dose_and_a_negation_and_the_set_covers_the_rest(path):
    feats = FEATURES[sets.set_language(path)]
    items = load(path)
    for it in items:
        assert re.search(feats["dose"], it["reference"]), f"{it['id']}: no drug dose"
        assert re.search(feats["negation"], it["reference"], re.I), f"{it['id']}: no negation"
    for name, least in MINIMUM.items():
        found = sum(bool(re.search(feats[name], it["reference"])) for it in items)
        assert found >= least, f"{name}: {found} items, want {least}"


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.stem)
def test_natural_speech_has_no_commands_and_some_hesitation(path):
    items = load(path)
    natural = [it for it in items if it["style"] == "natural"]
    for it in natural:
        assert not COMMAND_WORDS.search(it["spoken"]), it["id"]
        assert not re.search(FEATURES[sets.set_language(path)]["list"], it["reference"]), it["id"]
        assert '"' not in it["reference"], it["id"]
    assert sum(it["said"] != it["reference"] for it in natural) >= len(natural) // 2
    assert all(it["said"] == it["reference"] for it in items if it["style"] != "natural")


@pytest.mark.parametrize("path,item_id", cases())
def test_the_dictated_words_turn_back_into_the_text(path, item_id):
    """Said with every mark, each item converts back exactly; in its own style, words and layout do."""
    it = next(i for i in load(path) if i["id"] == item_id)
    language = sets.set_language(path)
    for stop in (sets.STOP_WORDS if language == "en" else ("period",)):
        assert back_to_text(sets.spoken_form(it["reference"], language=language, stop=stop), language) == it["reference"]
    assert unmarked(back_to_text(it["spoken"], language)) == unmarked(it["reference"])


@pytest.mark.parametrize("path", SETS, ids=lambda p: p.stem)
def test_kept_apart_from_the_evaluation_sets(path):
    """No patient or sentence from the sets behind the published figures."""
    text = "\n\n".join(it["reference"] for it in load(path))
    title = r"\b(?:Mr|Mrs|Ms|Miss|Dr|Sr|Sra|M|Dkt)\. ((?:[A-Z][\w'-]+ ?)+)"
    for other in EVALUATION_SETS:
        other_text = "\n\n".join(it["reference"] for it in load(other))
        for name in re.findall(title, other_text):
            surname = name.split()[-1]
            assert not re.search(rf"\b{re.escape(surname)}\b", text), f"{surname} from {other.name}"
        for sentence in re.split(r"(?<=[.?!])\s+", other_text):
            if len(words(sentence)) >= 8:
                assert sentence.strip() not in text, f"sentence from {other.name}"
