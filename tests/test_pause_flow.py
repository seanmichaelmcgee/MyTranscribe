"""pause_flow: sentence carry-over and command recovery from word timings (fictional text)."""

import pytest

import pause_flow as pf


def words(*items):
    """('text', start, end) triples -> faster-whisper style words (leading space)."""
    return [(" " + w, s, e) for w, s, e in items]


SENTENCES = words(("Atenolol", 0.2, 0.8), ("unchanged.", 0.9, 1.5),
                  ("No", 2.0, 2.2), ("swelling.", 2.3, 3.0),
                  ("The", 3.6, 3.7), ("patient", 3.8, 4.2), ("denies", 4.3, 4.8))


def test_words_text():
    assert pf.words_text(SENTENCES) == "Atenolol unchanged. No swelling. The patient denies"
    assert pf.words_text([]) == ""


def test_carry_holds_back_the_unfinished_sentence():
    keep, carry_from = pf.split_for_carry(SENTENCES, audio_s=8.0, max_carry_s=6.0)
    assert pf.words_text(keep) == "Atenolol unchanged. No swelling."
    assert 3.0 < carry_from < 3.6            # inside the pause after "swelling."


def test_chunk_final_full_stop_is_not_trusted():
    # The cut landed in a thinking pause; Whisper closed the clause with a full stop.
    cut = SENTENCES[:-1] + words(("denies.", 4.3, 4.8))
    keep, carry_from = pf.split_for_carry(cut, audio_s=8.0, max_carry_s=6.0)
    assert pf.words_text(keep) == "Atenolol unchanged. No swelling."
    assert carry_from is not None


def test_chunk_ending_on_a_command_is_kept_whole():
    ended = SENTENCES[:4] + words(("New", 3.6, 3.8), ("paragraph.", 3.8, 4.4))
    assert pf.split_for_carry(ended, audio_s=8.0, max_carry_s=6.0) == (ended, None)
    ended = SENTENCES[:4] + words(("unquote.", 3.6, 4.2))
    assert pf.split_for_carry(ended, audio_s=8.0, max_carry_s=6.0) == (ended, None)


def test_no_carry_when_the_last_sentence_end_is_too_far_back():
    keep, carry_from = pf.split_for_carry(SENTENCES, audio_s=20.0, max_carry_s=6.0)
    assert keep == SENTENCES and carry_from is None


def test_no_carry_without_a_pause_to_cut_in():
    run_on = words(("normal.", 0.0, 1.0), ("Continue", 1.05, 1.5), ("metformin", 1.6, 2.2))
    keep, carry_from = pf.split_for_carry(run_on, audio_s=3.0, max_carry_s=6.0)
    assert keep == run_on and carry_from is None


@pytest.mark.parametrize("chunk", [[], words(("Normal.", 0.1, 0.6)), words(("no", 0, 0.2), ("change", 0.3, 0.7))])
def test_short_or_unpunctuated_chunks_are_kept_whole(chunk):
    assert pf.split_for_carry(chunk, audio_s=1.0, max_carry_s=6.0) == (chunk, None)


def test_gaps_include_the_edges():
    gaps = pf.speech_gaps(SENTENCES, audio_s=8.0, min_gap_s=0.7)
    assert gaps == [(7, 4.8, 8.0)]
    assert [g[0] for g in pf.speech_gaps(SENTENCES, audio_s=8.0, min_gap_s=0.5)] == [2, 4, 7]
    assert pf.speech_gaps([], audio_s=2.0) == [(0, 0.0, 2.0)]


def test_rescue_holes_are_widened_and_in_time_order():
    w = words(("a.", 0.0, 0.5), ("b.", 1.5, 2.0), ("c.", 4.0, 4.5), ("d", 5.2, 5.5))
    holes = pf.rescue_holes(w, audio_s=5.6)
    assert [h[0] for h in holes] == [1, 2, 3]
    assert holes[1][1:3] == (2.0, 4.0)                         # the hole itself
    assert holes[1][3] == pytest.approx(2.0 - pf.RESCUE_MARGIN_S)
    assert holes[1][4] == pytest.approx(4.0 + pf.RESCUE_MARGIN_S)


@pytest.mark.parametrize("heard, want", [
    ([("New", 0.3, 0.5), ("paragraph.", 0.5, 1.0)], "New paragraph."),
    ([("normal.", 0.0, 0.3), ("New", 0.4, 0.6), ("paragraph.", 0.6, 1.1), ("Ibuprofen", 1.2, 1.9)],
     "New paragraph."),                                         # neighbours overlap the widened hole
    ([("or", 0.0, 0.1), ("rash.", 0.1, 0.4), ("New", 0.5, 0.7), ("paragraph.", 0.7, 1.2)],
     "New paragraph."),                                         # ...and are often cut mid-word
    ([("Next", 0.3, 0.5), ("line.", 0.5, 0.9)], "New line."),
    ([("Unquote.", 0.3, 0.9)], "close quote."),
])
def test_command_found_in_hole(heard, want):
    first_pass = words(("levels", 9.0, 9.5), ("are", 9.6, 10.0), ("normal.", 10.1, 10.8),
                       ("Ibuprofen", 12.9, 13.6), ("500", 13.7, 14.0))
    hit = pf.command_in_hole(words(*heard), first_pass, index=3)
    assert hit is not None and hit[0] == want
    assert hit[1] < hit[2]


@pytest.mark.parametrize("heard", [
    [("Thank", 0.3, 0.5), ("you.", 0.5, 0.8)],                  # the usual silence phantom
    [("paragraph.", 0.1, 0.5)],                                 # half a word is not a command
    [("um", 0.2, 0.4)],
    [],
    # A command inside a longer stretch of speech: not ours to add.
    [("we", 0.0, 0.1), ("will", 0.1, 0.2), ("start", 0.2, 0.3), ("a", 0.3, 0.4), ("new", 0.4, 0.6),
     ("line", 0.6, 0.9), ("of", 0.9, 1.0), ("therapy", 1.0, 1.5)],
])
def test_other_text_in_a_hole_is_ignored(heard):
    first_pass = words(("normal.", 10.1, 10.8), ("Ibuprofen", 12.9, 13.6))
    assert pf.command_in_hole(words(*heard), first_pass, index=1) is None


def test_command_already_in_the_text_is_not_added_twice():
    first_pass = words(("normal.", 10.1, 10.8), ("New", 11.0, 11.2), ("paragraph.", 11.2, 11.7),
                       ("Ibuprofen", 12.9, 13.6))
    heard = words(("New", 0.2, 0.4), ("paragraph.", 0.4, 0.9))
    assert pf.command_in_hole(heard, first_pass, index=3) is None


def test_second_listen_must_be_sure_of_the_command():
    first_pass = words(("normal.", 10.1, 10.8), ("Ibuprofen", 12.9, 13.6))
    heard = [(" New", 0.2, 0.4, 0.12), (" paragraph.", 0.4, 0.9, 0.91)]     # low first word is normal
    assert pf.command_in_hole(heard, first_pass, index=1)[0] == "New paragraph."
    guessed = [(" New", 0.2, 0.4, 0.10), (" line.", 0.4, 0.6, 0.35)]        # prompted, not heard
    assert pf.command_in_hole(guessed, first_pass, index=1) is None


def test_command_near():
    w = words(("normal.", 1.0, 1.5), ("New", 1.6, 1.7), ("paragraph.", 1.7, 1.8), ("Next", 3.0, 3.4),
              ("visit", 3.5, 3.9), ("in", 4.0, 4.1), ("six", 4.2, 4.5), ("weeks.", 4.6, 5.0), ("Bloods", 6.5, 7.0))
    assert pf.command_near(w, 3)                               # hole right after the command
    assert not pf.command_near(w, 8)                           # far enough away
    assert not pf.command_near([], 0)


def test_insert_commands_keeps_order():
    base = words(("normal.", 1.0, 1.5), ("Ibuprofen", 3.5, 4.2), ("daily.", 4.3, 4.8), ("Review", 7.0, 7.5))
    out = pf.insert_commands(base, [(1, 2.0, 2.8, "New paragraph."), (3, 5.5, 6.2, "New line.")])
    assert pf.words_text(out) == "normal. New paragraph. Ibuprofen daily. New line. Review"
    # A recovered command is a sentence end the carry logic can cut after.
    keep, carry_from = pf.split_for_carry(out, audio_s=8.0, max_carry_s=6.0)
    assert pf.words_text(keep).endswith("New line.") and 6.2 < carry_from < 7.0
