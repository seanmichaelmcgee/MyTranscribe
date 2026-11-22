"""
qt_gc.py — Python's garbage collection on the GUI thread only.

Python's cyclic garbage collector runs in whichever thread happens to allocate. When it frees a
Qt object (a window, a dialog, a timer) on one of the app's background threads (audio capture,
transcription), Qt destroys that object off the thread it belongs to, which Qt does not allow:
with PySide6 the process aborts. Found 2026-11-22 when the tests, which make and drop many
windows, aborted at random points under PySide6 and never with collection off.

So automatic collection is switched off and the GUI thread collects on a timer, with the same
generation thresholds Python would use (the approach pyqtgraph takes). Objects freed by
reference counting are unaffected.
"""

import gc

from PySide6.QtCore import QObject, QTimer

INTERVAL_MS = 1000


class GuiThreadCollector(QObject):
    """Create once, on the GUI thread, after the QApplication; keep a reference."""

    def __init__(self, interval_ms: int = INTERVAL_MS, parent=None) -> None:
        super().__init__(parent)
        self.threshold = gc.get_threshold()
        gc.disable()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(interval_ms)

    def check(self) -> None:
        """Collect the generations whose counts have passed Python's own thresholds."""
        c0, c1, c2 = gc.get_count()
        if c0 > self.threshold[0]:
            gc.collect(0)
            if c1 > self.threshold[1]:
                gc.collect(1)
                if c2 > self.threshold[2]:
                    gc.collect(2)
