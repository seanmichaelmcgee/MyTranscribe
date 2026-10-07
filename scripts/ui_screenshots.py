"""
ui_screenshots.py — render the gui_med window and Options screen to PNGs.

Uses a fake engine and fictional text; no microphone, model, clipboard or
global hooks needed. Settings go to a temporary file.

    venv1060\\Scripts\\python.exe scripts\\ui_screenshots.py --out results_1060\\ui
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

SAMPLE = ("Subjective: 58-year-old with type 2 diabetes and hypertension here for follow-up. "
          "Home readings average 138 over 84. No chest pain or dyspnea. "
          "Plan: increase lisinopril to 20 mg daily, continue metformin 1000 mg twice daily, "
          "repeat A1c and urine albumin-to-creatinine ratio in three months.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "results_1060" / "ui")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    for old in args.out.glob("*.png"):
        old.unlink()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication
    import gui_qt
    import gui_med
    from fakes import EndlessStream, FakeClipboard, FakeEngine, speech_like
    from options_dialog import OptionsDialog
    from settings import Settings

    gui_qt.HotkeyBridge.start = lambda self: None
    gui_qt.HotkeyBridge.stop = lambda self: None
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(gui_med.MED_QSS)

    def pump(s):
        end = time.time() + s
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    w = gui_med.MedTranscriptionWindow(
        engine_factory=lambda: FakeEngine(text_fn=lambda i, a: SAMPLE),
        stream_factory=lambda: (EndlessStream(speech_like(3), pace_s=0.002), None),
        autopaste=False, base_prompt="", text_pipeline=(None, None),
        settings=Settings(start_compact=True), install_hooks=False,
        settings_path=Path(tempfile.gettempdir()) / "mytranscribe_screens.json")
    w._chime.play_start = w._chime.play_end = lambda: None
    clip = FakeClipboard()
    w._clipboard = lambda: clip
    w._clipboard_seq = clip.sequence
    w.show()
    pump(1.0)

    def shot(name, widget=None):
        pump(0.3)
        path = args.out / f"{name}.png"
        (widget or w).grab().save(str(path))
        print("wrote", path)

    shot("1_compact_ready")
    w._triggers.handle("key", "down")           # F9 held
    pump(0.6)
    shot("2_compact_recording")
    w._triggers.handle("key", "up")
    while w._finishing:
        pump(0.1)
    shot("3_compact_copied")
    w._toggle_compact()                         # "+"
    pump(0.3)
    shot("4_expanded_copied")
    clip.setText("previous contents")
    clip.reject_writes = -1
    w._on_copy_clicked()
    pump(1.0)
    shot("5_expanded_not_copied")
    clip.reject_writes = 0

    dlg = OptionsDialog(w._settings, parent=w)
    dlg.show()
    pump(0.5)
    shot("6_options", dlg)
    dlg.close()
    w.close()


if __name__ == "__main__":
    main()
