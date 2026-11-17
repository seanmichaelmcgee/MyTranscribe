"""validation_tool: the reading set and its dictated form (no microphone, other dictation software or model)."""

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


def test_import_takes_recordings_named_by_item_code(tmp_path, capsys, monkeypatch):
    import argparse
    import wave
    import numpy as np

    def fake_load(path):                                        # stands in for the real decoder (no model libraries in tests)
        with wave.open(str(path)) as w:
            pcm = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float32) / 32768
            return pcm[::w.getframerate() // 16000][:16000 * 60] if w.getframerate() != 16000 else pcm
    monkeypatch.setattr(vt, "load_audio", fake_load)
    src, out = tmp_path / "drive", tmp_path / "session"
    src.mkdir()
    tone = (np.sin(np.arange(44100) * 0.05) * 8000).astype("<i2")
    for name in ("S01.wav", "c03.wav", "holiday.wav"):
        with wave.open(str(src / name), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)                               # not the app's rate: must be converted
            w.writeframes(tone.tobytes())
    (src / "s01.other.txt").write_text("Please let her know.", encoding="utf-8")
    (src / "holiday.wav").rename(src / "holiday.txt")       # not audio: ignored (a long recording needs a model)
    vt.cmd_import(argparse.Namespace(**{"set": vt.DEFAULT_SET, "from": src, "out": out, "model": None}))
    with wave.open(str(out / "items" / "s01.wav")) as w:
        assert (w.getframerate(), w.getnchannels()) == (16000, 1) and w.getnframes() > 10000
    assert (out / "items" / "c03.wav").is_file() and not (out / "items" / "holiday.wav").exists()
    assert (out / "items" / "s01.other.txt").read_text(encoding="utf-8") == "Please let her know."
    printed = capsys.readouterr().out
    assert "2 of 28 items imported" in printed and "still missing" in printed


def _timed(text, start=0.0, step=0.4):
    return [(" " + w, start + i * step, start + i * step + 0.3) for i, w in enumerate(text.split())]


def test_break_break_cuts_one_long_recording_into_pieces():
    words = (_timed("Noted comma confirming receipt of report period")
             + _timed("Break, break.", 5.0)
             + _timed("Results reviewed comma no action needed period", 7.0)
             + _timed("brake break break", 12.0)
             + _timed("Please take a break from lifting period", 15.0))          # one "break" alone is just a word
    assert [(round(a, 1), round(b, 1)) for a, b in vt.find_breaks(words)] == [(5.0, 5.7), (12.0, 13.1)]
    pieces = vt.split_pieces(words, 20.0)
    assert [p[2].split()[0] for p in pieces] == ["Noted", "Results", "Please"]
    assert pieces[0][1] < 5.0 and pieces[1][0] > 5.7                            # the break itself is cut out


def test_pieces_are_matched_to_items_by_what_was_said_and_a_reread_wins():
    items = vt.load_set(vt.DEFAULT_SET)
    by = {it["id"]: it["spoken"] for it in items}
    pieces = [(0, 5, by["s02"]),                                   # out of order
              (6, 9, "um sorry noted confirming"),                 # a false start: matches nothing well enough
              (10, 20, by["s04"].replace("reviewed", "revued")),   # a stumble ...
              (21, 31, by["s04"]),                                 # ... read again: this one is kept
              (32, 40, "something else entirely about the weather today and tomorrow")]
    assert vt.match_pieces(pieces, items) == {"s02": 0, "s04": 3}


def test_a_false_start_before_sorry_break_break_is_cut_off():
    words = (_timed("I would be grateful period Thank you period")
             + _timed("Thank you for seeing Mrs sorry", 4.0)
             + _timed("break break", 7.0)
             + _timed("Thank you for seeing Mrs Dolores Whitcombe comma a 67-year-old woman", 9.0))
    pieces = vt.split_pieces(words, 20.0)
    assert pieces[0][2] == "I would be grateful period Thank you period"
    assert pieces[0][1] < 4.0                                   # the abandoned words are not in the first clip
    assert pieces[1][2].startswith("Thank you for seeing Mrs Dolores")


def test_an_item_that_ends_like_the_next_one_begins_is_not_cut():
    words = (_timed("I suspect irritable bowel syndrome period Thank you for seeing her period")
             + _timed("break break", 6.0)
             + _timed("Thank you for seeing Mr Gordon Tanaka comma a 72-year-old man", 8.0))
    assert vt.split_pieces(words, 20.0)[0][2].endswith("Thank you for seeing her period")
