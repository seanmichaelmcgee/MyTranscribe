"""triggers: config parsing and raw Windows event classification (no hooks installed)."""

import triggers as tr

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN = 0x0100, 0x0101, 0x0104
WM_MBUTTONDOWN, WM_XBUTTONDOWN, WM_XBUTTONUP = 0x0207, 0x020B, 0x020C
VK_F9, VK_F8, VK_PAUSE = 0x78, 0x77, 0x13


def test_config_defaults_and_env():
    c = tr.TriggerConfig.from_env({})
    assert (c.key, c.mouse, c.hold) == ("f9", "x2", False)
    c = tr.TriggerConfig.from_env({"MYTRANSCRIBE_KEY": "Pause", "MYTRANSCRIBE_MOUSE": "none",
                                   "MYTRANSCRIBE_TRIGGER_MODE": "hold"})
    assert (c.key, c.mouse, c.hold) == ("pause", None, True)
    c = tr.TriggerConfig.from_env({"MYTRANSCRIBE_KEY": "ctrl", "MYTRANSCRIBE_MOUSE": "left"})
    assert c.key is None and c.mouse is None          # unsafe/unknown values are refused


def test_describe():
    assert tr.TriggerConfig("f9", "x2").describe() == "F9 · mouse forward button"
    assert tr.TriggerConfig("scroll_lock", None).describe() == "Scroll Lock"
    assert tr.TriggerConfig(None, None).describe() == ""


def test_classify_key(qapp):
    t = tr.InputTriggers(tr.TriggerConfig("f9", None))
    assert t.classify_key(WM_KEYDOWN, VK_F9) == "down"
    assert t.classify_key(WM_SYSKEYDOWN, VK_F9) == "down"      # with Alt held
    assert t.classify_key(WM_KEYUP, VK_F9) == "up"
    assert t.classify_key(WM_KEYDOWN, VK_F8) is None
    assert tr.InputTriggers(tr.TriggerConfig("pause", None)).classify_key(WM_KEYDOWN, VK_PAUSE) == "down"
    assert tr.InputTriggers(tr.TriggerConfig(None, "x2")).classify_key(WM_KEYDOWN, VK_F9) is None


def test_classify_mouse(qapp):
    x2 = tr.InputTriggers(tr.TriggerConfig(None, "x2"))
    assert x2.classify_mouse(WM_XBUTTONDOWN, 2 << 16) == "down"
    assert x2.classify_mouse(WM_XBUTTONUP, 2 << 16) == "up"
    assert x2.classify_mouse(WM_XBUTTONDOWN, 1 << 16) is None          # back button untouched
    assert x2.classify_mouse(WM_MBUTTONDOWN, 0) is None
    mid = tr.InputTriggers(tr.TriggerConfig(None, "middle"))
    assert mid.classify_mouse(WM_MBUTTONDOWN, 0) == "down"


def test_handle_debounces_autorepeat_and_hold(qapp):
    t = tr.InputTriggers(tr.TriggerConfig("f9", None, hold=False))
    got = []
    t.pressed.connect(lambda: got.append("p"))
    t.released.connect(lambda: got.append("r"))
    for edge in ("down", "down", "down", "up", "down", "up"):
        t.handle(edge)
    assert got == ["p", "p"]                          # toggle: repeats ignored, no releases
    h = tr.InputTriggers(tr.TriggerConfig("f9", None, hold=True))
    got2 = []
    h.pressed.connect(lambda: got2.append("p"))
    h.released.connect(lambda: got2.append("r"))
    for edge in ("down", "down", "up"):
        h.handle(edge)
    assert got2 == ["p", "r"]
