"""live_insert: typing the transcript as it grows, without losing what depends on the next piece."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import live_insert as li  # noqa: E402
import voice_commands as vc  # noqa: E402

from conftest import wait_for  # noqa: E402
from fakes import FakeEngine  # noqa: E402


def typed(pieces, fmt=lambda t: vc.apply(t, lenient=True, punctuation=True)):
    doc, done = "", []
    for p in pieces:
        done.append(p)
        doc += li.next_text(doc, fmt(" ".join(done)))
    return doc + li.next_text(doc, fmt(" ".join(done)), final=True)


def test_a_paragraph_at_the_end_of_a_piece_is_kept():
    pieces = ["He settled, period. New paragraph.", "On examination, comma, pulse 88, period."]
    fmt = lambda t: vc.apply(t, lenient=True, punctuation=True)
    assert typed(pieces) == fmt(" ".join(pieces)) == "He settled.\n\nOn examination, pulse 88."


def test_a_hesitation_before_the_next_piece_is_cleaned_up():
    pieces = ["She did not tolerate...", "dulaglutide because of nausea, period."]
    assert typed(pieces) == "She did not tolerate dulaglutide because of nausea."


def test_typing_follows_the_copied_text_piece_by_piece():
    doc = li.next_text("", "Piece 0.")
    assert doc == "Piece 0"                                               # the last mark waits for what follows
    assert li.next_text(doc, "Piece 0. Piece 1.") == ". Piece 1"
    assert li.next_text("Piece 0", "Piece 0.\n\n") == ""
    assert li.next_text("Piece 0", "Piece 0.\n\nPiece 1.") == ".\n\nPiece 1"
    assert li.next_text("Piece 0", "Piece 0.", final=True) == "."         # Stop types the rest


def test_a_full_stop_that_becomes_a_comma_is_not_typed_early():
    pieces = ["Thank you for seeing Mr. Okafor.", "comma, a 71-year-old man, period."]
    fmt = lambda t: vc.apply(t, lenient=True, punctuation=True)
    assert typed(pieces) == fmt(" ".join(pieces))


@pytest.mark.parametrize("typed_so_far, full, want", [
    ("Started, It was", "Started, it was quiet.", " quiet."),          # earlier text changed: carry on by words
    ("One two three", "One two", ""),
    ("", "Hello.", "Hello."),
])
def test_when_typed_text_no_longer_matches_it_continues_after_the_same_words(typed_so_far, full, want):
    assert li.next_text(typed_so_far, full, final=True) == want


def test_shorter_windows_only_while_typing_as_you_dictate(qapp, tmp_path, monkeypatch):
    import gui_qt
    import gui_med
    from dataclasses import replace
    from chunked_transcriber import CHUNK_TARGET_S
    from fakes import EndlessStream, speech_like
    from settings import Settings
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    w = gui_med.MedTranscriptionWindow(
        engine_factory=FakeEngine, stream_factory=lambda: (EndlessStream(speech_like(1)), None),
        base_prompt="", text_pipeline=(None, None), settings=Settings(start_compact=False, live_insert=False),
        settings_path=tmp_path / "s.json", install_hooks=False)
    try:
        assert wait_for(lambda: w.ready, app=qapp)
        assert w._transcriber.chunk_target_s == CHUNK_TARGET_S == 30.0
        w.apply_settings(replace(w._settings, live_insert=True))
        assert w._transcriber.chunk_target_s == gui_med.LIVE_INSERT_CHUNK_S == 15.0
        assert w._transcriber.cut_search_s == 5.0
        w.apply_settings(replace(w._settings, live_insert=False))
        assert w._transcriber.chunk_target_s == 30.0
    finally:
        w.close()


def test_window_types_paragraphs_across_pieces(qapp, tmp_path, monkeypatch):
    import gui_qt
    import gui_med
    import phi_clipboard
    from fakes import EndlessStream, FakeClipboard, speech_like
    from settings import Settings
    monkeypatch.setattr(gui_qt.HotkeyBridge, "start", lambda self: None)
    monkeypatch.setattr(gui_qt.HotkeyBridge, "stop", lambda self: None)
    monkeypatch.setattr(phi_clipboard, "send_paste", lambda *a, **k: None)
    monkeypatch.setattr(phi_clipboard, "modifiers_held", lambda *a, **k: False)
    texts = lambda i, a: "Piece zero, period. New paragraph." if i == 0 else f"Piece {i}, period."
    w = gui_med.MedTranscriptionWindow(
        engine_factory=lambda: FakeEngine(text_fn=texts), stream_factory=lambda: (EndlessStream(speech_like(3), pace_s=0.002), None),
        autopaste=False, base_prompt="", text_pipeline=(None, None),
        settings=Settings(start_compact=False, live_insert=True, spoken_punctuation=True, extra_fixes=False),
        settings_path=tmp_path / "s.json", install_hooks=False, mic_warmup_s=0)
    try:
        w.clip = FakeClipboard()
        w._clipboard = lambda: w.clip
        w._clipboard_seq = w.clip.sequence
        w._foreground = lambda: 4242
        assert wait_for(lambda: w.ready, app=qapp)
        w._transcriber.chunk_target_s = 0.5
        w.on_hotkey()
        assert wait_for(lambda: len(w.inserted_pieces) >= 2, timeout=5, app=qapp)
        w.on_hotkey()
        assert wait_for(lambda: not w._finishing and w.copy_ok is True, timeout=5, app=qapp)
        wait_for(lambda: False, timeout=0.5, app=qapp)
        joined = "".join(w.inserted_pieces)
        assert joined.startswith("Piece zero.\n\nPiece 1.")
        assert joined == w._text_area.toPlainText() == w.clip.text()
    finally:
        w.close()
