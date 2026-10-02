"""Shared pytest setup: put src/ on sys.path, provide fakes and a Qt app."""

import os
import sys
import time
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def wait_for(cond, timeout=5.0, interval=0.01, app=None):
    """Poll `cond` until true (pumping Qt events if app given). Returns final value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if cond():
            return True
        time.sleep(interval)
    if app is not None:
        app.processEvents()
    return bool(cond())


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole run. GUI tests need an X display (xvfb-run)."""
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        pytest.skip("GUI tests need a display; run under xvfb-run")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
