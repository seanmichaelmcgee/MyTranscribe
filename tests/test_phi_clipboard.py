"""phi_clipboard: Windows privacy clipboard formats, modifier wait, paste keys."""

import phi_clipboard as pc


def test_privacy_entries_only_on_windows():
    assert pc.privacy_mime_entries("linux") == {}
    entries = pc.privacy_mime_entries("win32")
    assert set(entries) == {
        'application/x-qt-windows-mime;value="ExcludeClipboardContentFromMonitorProcessing"',
        'application/x-qt-windows-mime;value="CanIncludeInClipboardHistory"',
        'application/x-qt-windows-mime;value="CanUploadToCloudClipboard"',
    }
    assert entries['application/x-qt-windows-mime;value="CanUploadToCloudClipboard"'] == b"\0\0\0\0"


def test_mime_data_carries_text_and_markers(qapp):
    mime = pc.make_mime_data("Dear Dr. Patel", platform="win32")
    assert mime.text() == "Dear Dr. Patel"
    assert mime.hasFormat('application/x-qt-windows-mime;value="CanIncludeInClipboardHistory"')


def test_copy_text_roundtrip(qapp):
    cb = qapp.clipboard()
    pc.copy_text(cb, "Plan: Holter monitor.")
    assert cb.text() == "Plan: Holter monitor."


def test_copy_text_reports_failure(qapp):
    from fakes import FakeClipboard
    ok = FakeClipboard("old")
    assert pc.copy_text(ok, "new text") is True and ok.text() == "new text"
    busy = FakeClipboard("old", reject_writes=-1)
    assert pc.copy_text(busy, "new text") is False and busy.text() == "old"


def test_copy_text_never_reads_a_busy_clipboard_when_sequence_available(qapp):
    """Reading a clipboard another program holds blocks Qt ~0.6 s: skip it."""
    from fakes import FakeClipboard
    busy = FakeClipboard("old", reject_writes=-1)
    assert pc.copy_text(busy, "new", sequence=busy.sequence) is False
    assert busy.reads == 0
    free = FakeClipboard("old")
    assert pc.copy_text(free, "new", sequence=free.sequence) is True and free.reads == 1


def test_modifiers_held():
    assert pc.modifiers_held("linux") is False
    down = {0x11}
    state = lambda vk: 0x8000 if vk in down else 0
    assert pc.modifiers_held("win32", get_key_state=state) is True
    down.clear()
    assert pc.modifiers_held("win32", get_key_state=state) is False


class RecordingController:
    def __init__(self):
        self.events = []

    def press(self, k):
        self.events.append(("press", str(k)))

    def release(self, k):
        self.events.append(("release", str(k)))


def test_send_paste_sequence():
    kb = RecordingController()
    pc.send_paste(kb, platform="win32")
    assert kb.events == [("press", "Key.ctrl"), ("press", "v"),
                         ("release", "v"), ("release", "Key.ctrl")]
