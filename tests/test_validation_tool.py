"""validation_tool: the reading set and its dictated form (no microphone, Dragon or model)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import text_fixes  # noqa: E402
import validation_tool as vt  # noqa: E402
import voice_commands  # noqa: E402


def test_set_has_short_messages_and_consult_notes():
    items = vt.load_set(vt.DEFAULT_SET)
    kinds = [it["category"] for it in items]
    assert kinds.count("short") == 20 and kinds.count("consult") == 8
    assert len({it["id"] for it in items}) == len(items)
    assert all(it["reference"] and "#" not in it["reference"] for it in items)
    assert all(it["reference"].count("\n\n") >= 2 for it in items if it["category"] == "consult")   # paragraphs


def test_dictated_form_says_every_mark_and_break():
    said = vt.spoken_form('Seen today, BP 142/86, A1c 7.2%.\n\n"Recheck".\nPlan:\n1. Rest.', shout=True)
    assert said == ("Seen today COMMA BP 142 over 86 COMMA A1c 7.2 percent PERIOD NEW PARAGRAPH "
                    "OPEN QUOTE Recheck CLOSE QUOTE PERIOD NEW LINE Plan COLON NEW LINE 1 PERIOD Rest PERIOD")
    assert vt.spoken_form("Thank you for seeing Mr. Lee, aged 4.5.") == \
        "Thank you for seeing Mr. Lee comma aged 4.5 period"          # title and decimal keep their dots


def test_the_app_turns_every_dictated_item_back_into_its_text():
    """What you are asked to say, converted by the app's own rules, is exactly what should appear."""
    for item in vt.load_set(vt.DEFAULT_SET):
        got = voice_commands.apply(text_fixes.format_readings(item["spoken"]), lenient=True, punctuation=True)
        assert got == item["reference"], item["id"]


def test_parse_ignores_the_header_and_keeps_blank_lines_inside_items():
    items = vt.parse_set("# note\n\n## a | short\nOne.\n\nTwo.\n\n## b | consult\nThree.\n")
    assert [(i["id"], i["category"], i["reference"]) for i in items] == [("a", "short", "One.\n\nTwo."),
                                                                         ("b", "consult", "Three.")]


def test_adjusted_count_forgives_spelling_variants_and_split_words_only():
    ref = "It was okay, 2 colours, long-standing heartburn behind the breastbone, follow-up first."
    hyp = "It was ok, 2 colors, longstanding heartburn behind the breast bone, followup 1st."
    assert vt.adjusted_errors(ref, hyp) == 0
    assert vt.adjusted_errors(ref, hyp.replace("heartburn", "heartbeat")) == 1      # a real mistake still counts
    assert vt.adjusted_errors("apixaban 5 mg", "ativan 5 mg") == 1
    assert vt.adjusted_errors("the breast bone", "the bone") == 1
