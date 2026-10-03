"""triggers: config and raw Windows event classification (no hooks installed)."""

import triggers as tr

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN = 0x0100, 0x0101, 0x0104
WM_MBUTTONDOWN, WM_XBUTTONDOWN, WM_XBUTTONUP = 0x0207, 0x020B, 0x020C
VK_F9, VK_F8, VK_PAUSE = 0x78, 0x77, 0x13


def test_config_defaults_and_validation():
    c = tr.TriggerConfig()
    assert (c.key, c.key_hold, c.mouse, c.mouse_hold) == ("f9", True, "x2", False)
    c = tr.TriggerConfig(key="ctrl", mouse="left")
    assert c.key is None and c.mouse is None          # unsafe/unknown values are refused
    assert c.hold_for("key") is True and tr.TriggerConfig().hold_for("mouse") is False


def test_describe_and_labels():
    assert tr.TriggerConfig().describe() == [("F9", "hold to talk"), ("Mouse forward button", "toggle")]
    assert tr.key_label("scroll_lock") == "Scroll Lock" and tr.key_label(None) == "None"
    assert tr.TriggerConfig(key=None, mouse=None).describe() == []


def test_classify_key(qapp):
    t = tr.InputTriggers(tr.TriggerConfig(key="f9", mouse=None))
    assert t.classify_key(WM_KEYDOWN, VK_F9) == "down"
    assert t.classify_key(WM_SYSKEYDOWN, VK_F9) == "down"      # with Alt held
    assert t.classify_key(WM_KEYUP, VK_F9) == "up"
    assert t.classify_key(WM_KEYDOWN, VK_F8) is None
    assert tr.InputTriggers(tr.TriggerConfig(key="pause")).classify_key(WM_KEYDOWN, VK_PAUSE) == "down"
    assert tr.InputTriggers(tr.TriggerConfig(key=None)).classify_key(WM_KEYDOWN, VK_F9) is None


def test_classify_mouse(qapp):
    x2 = tr.InputTriggers(tr.TriggerConfig(key=None, mouse="x2"))
    assert x2.classify_mouse(WM_XBUTTONDOWN, 2 << 16) == "down"
    assert x2.classify_mouse(WM_XBUTTONUP, 2 << 16) == "up"
    assert x2.classify_mouse(WM_XBUTTONDOWN, 1 << 16) is None          # back button untouched
    assert x2.classify_mouse(WM_MBUTTONDOWN, 0) is None
    mid = tr.InputTriggers(tr.TriggerConfig(key=None, mouse="middle"))
    assert mid.classify_mouse(WM_MBUTTONDOWN, 0) == "down"


def test_handle_debounces_autorepeat_per_source(qapp):
    t = tr.InputTriggers(tr.TriggerConfig())
    got = []
    t.pressed.connect(lambda s: got.append(("p", s)))
    t.released.connect(lambda s: got.append(("r", s)))
    for src, edge in (("key", "down"), ("key", "down"), ("mouse", "down"), ("key", "up"),
                      ("mouse", "up"), ("key", "down")):
        t.handle(src, edge)
    assert got == [("p", "key"), ("p", "mouse"), ("r", "key"), ("r", "mouse"), ("p", "key")]
