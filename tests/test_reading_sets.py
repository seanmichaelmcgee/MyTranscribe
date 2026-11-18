"""tuning.sets: how each kind of speaker dictates a written text, and the set file format."""

import pytest

import text_fixes
import voice_commands
from tuning import sets

SAMPLE = 'Seen today, BP 142/86, A1c 7.2%.\n\n"Recheck".\nPlan:\n1. Rest.'


def back_to_text(spoken: str) -> str:
    """What the app's own rules make of the dictated words."""
    return voice_commands.apply(text_fixes.format_readings(spoken), lenient=True, punctuation=True)


def test_every_mark_with_full_stop():
    assert sets.spoken_form(SAMPLE, shout=True, stop="full stop") == (
        "Seen today COMMA BP 142 over 86 COMMA A1c 7.2 percent FULL STOP NEW PARAGRAPH "
        "OPEN QUOTE Recheck CLOSE QUOTE FULL STOP NEW LINE Plan COLON NEW LINE 1 FULL STOP Rest FULL STOP")


def test_sentence_marks_leave_the_commas_unsaid():
    assert sets.spoken_form(SAMPLE, mode="sentence") == (
        "Seen today, BP 142 over 86, A1c 7.2 percent period new paragraph "
        "open quote Recheck close quote period new line Plan colon new line 1 period Rest period")


def test_layout_says_only_breaks_quotes_and_list_numbers():
    assert sets.spoken_form(SAMPLE, mode="layout") == (
        "Seen today, BP 142 over 86, A1c 7.2 percent. new paragraph "
        "open quote Recheck close quote. new line Plan: new line 1 period Rest.")


def test_natural_says_no_commands_and_keeps_paragraphs_as_pauses():
    said = sets.spoken_form("No fever, no cough.\n\nReview in 2 weeks.", mode="natural")
    assert said == "No fever, no cough.\n\nReview in 2 weeks."


ROUND_TRIP = 'Seen today, BP 142/86, pulse 72.\n\n"Recheck".\nPlan:\n1. Rest.'


@pytest.mark.parametrize("mode", ["every", "sentence", "layout"])
@pytest.mark.parametrize("stop", sets.STOP_WORDS)
def test_the_app_turns_each_way_of_dictating_back_into_the_text(mode, stop):
    expected = ROUND_TRIP
    if mode == "layout":
        # The app drops the model's , ; : before a spoken line break, so a speaker who
        # says no marks gets "Plan" without its colon; saying "colon" keeps it.
        expected = ROUND_TRIP.replace("Plan:\n", "Plan\n")
    assert back_to_text(sets.spoken_form(ROUND_TRIP, mode=mode, stop=stop)) == expected


def test_a_dictated_comma_keeps_a_mixed_case_term():
    # Was lower-cased to "a1c" until 2026-11-18 (found while writing the synthetic set).
    assert back_to_text("Seen today comma A1c 7.2 percent period") == "Seen today, A1c 7.2%."


def test_hesitations_are_said_but_not_written():
    item = sets.parse_set("## n01 | letter | natural | tune\nShe has {um} had 2 falls.\n")[0]
    assert (item["reference"], item["said"], item["spoken"]) == (
        "She has had 2 falls.", "She has um had 2 falls.", "She has um had 2 falls.")
    assert (item["style"], item["split"]) == ("natural", "tune")


def test_old_two_field_headers_still_read_with_every_mark():
    item = sets.parse_set("## a | short\nOkay, thanks.\n")[0]
    assert (item["category"], item["style"], item["split"], item["spoken"]) == (
        "short", None, None, "Okay comma thanks period")


def test_unknown_style_or_split_is_an_error():
    with pytest.raises(ValueError):
        sets.parse_set("## x | letter | shouting | tune\nHi.\n")
    with pytest.raises(ValueError):
        sets.parse_set("## x | letter | every | maybe\nHi.\n")


def test_other_languages_take_the_words_from_their_pack():
    assert sets.spoken_form("Sin fiebre, sin tos.", language="es", mode="sentence") == "Sin fiebre, sin tos punto"
    assert sets.spoken_form("Sin fiebre, sin tos.", language="es") == "Sin fiebre coma sin tos punto"
