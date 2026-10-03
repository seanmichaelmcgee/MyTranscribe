"""
ui_screenshots.py — render the gui_med window in its main states to PNGs.

Uses a fake engine and fictional text; no microphone, model or clipboard needed.

    venv1060\\Scripts\\python.exe scripts\\ui_screenshots.py --out results_1060\\ui
"""

import argparse
import sys
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

    from PyQt6.QtWidgets import QApplication
    import gui_qt
    import gui_med
    from fakes import EndlessStream, FakeClipboard, FakeEngine, speech_like
    from triggers import TriggerConfig

    gui_qt.HotkeyBridge.start = lambda self: None
    gui_qt.HotkeyBridge.stop = lambda self: None
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(gui_med.MED_QSS)

    def pump(s):
        end = time.time() + s
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    cfg = TriggerConfig("f9", "x2", hold=False)
    cfg_start, cfg_stop = gui_med.InputTriggers.start, gui_med.InputTriggers.stop
    gui_med.InputTriggers.start = gui_med.InputTriggers.stop = lambda self: None
    w = gui_med.MedTranscriptionWindow(
        engine_factory=lambda: FakeEngine(text_fn=lambda i, a: SAMPLE),
        stream_factory=lambda: (EndlessStream(speech_like(3), pace_s=0.002), None),
        autopaste=False, base_prompt="", text_pipeline=(None, None), trigger_config=cfg)
    w._chime.play_start = w._chime.play_end = lambda: None
    clip = FakeClipboard()
    w._clipboard = lambda: clip
    w.show()
    pump(1.0)

    def shot(name):
        pump(0.3)
        path = args.out / f"{name}.png"
        w.grab().save(str(path))
        print("wrote", path)

    shot("1_ready")
    w._on_toggle_clicked()
    pump(0.8)
    w._text_area.setPlainText(SAMPLE[:120])
    w._audio_indicator.setVisible(True)
    shot("2_recording")
    w._on_toggle_clicked()
    while w._finishing:
        pump(0.1)
    shot("3_copied")
    clip.setText("previous contents")
    clip.reject_writes = -1
    w._on_copy_clicked()
    pump(1.0)
    shot("4_not_copied")
    clip.reject_writes = 0
    w._on_copy_clicked()
    pump(0.3)
    w._toggle_compact()
    pump(0.3)
    shot("5_compact")
    w.close()
    gui_med.InputTriggers.start, gui_med.InputTriggers.stop = cfg_start, cfg_stop


if __name__ == "__main__":
    main()
