"""Garbage collection runs on the GUI thread only (qt_gc.py): Qt objects must not be freed elsewhere."""

import gc
import threading


def test_collection_is_off_until_the_gui_thread_collects(qapp):
    from qt_gc import GuiThreadCollector
    collector = GuiThreadCollector(interval_ms=60_000)
    try:
        assert not gc.isenabled()                       # never on a background thread by itself

        def make_cycles():
            for _ in range(collector.threshold[0] * 2):
                node = {}
                node["self"] = node                     # garbage only the cyclic collector can free

        worker = threading.Thread(target=make_cycles)
        worker.start()
        worker.join()
        assert gc.get_count()[0] > collector.threshold[0]   # the worker's allocations did not collect
        collector.check()                               # on this (the GUI) thread
        assert gc.get_count()[0] < collector.threshold[0]
    finally:
        collector.timer.stop()
