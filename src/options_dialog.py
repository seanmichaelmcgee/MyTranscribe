"""
options_dialog.py — the Options screen for gui_med.py.

Shows which keys start/stop dictation, lets the user change the single key,
the mouse button and hold-to-talk vs toggle for each, the start-up view, and
gives a short how-to. Returns an edited copy of settings.Settings; the caller
saves and applies it. New options belong here, not on the main window.
"""

from dataclasses import replace

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QLabel, QVBoxLayout,
)

from settings import Settings
from triggers import KEY_CHOICES, MOUSE_CHOICES, key_label

MODES = [("hold", "Hold to talk"), ("toggle", "Toggle (press to start, press to stop)")]

HOW_TO = (
    "<b>How it works</b><br>"
    "Dictate, then stop. The text is transcribed on this PC while you speak "
    "(nothing leaves the computer) and copied to the clipboard when you stop. "
    "Click in your EMR and press <b>Ctrl+V</b>.<br><br>"
    "The light at the top left is <b><span style='color:#2E9E4F'>green while recording</span></b> "
    "and <b><span style='color:#C8322B'>red when not</span></b>.<br>"
    "If the status says <b>Not copied</b>, another program was using the clipboard: "
    "click <b>Copy</b> and paste again.<br>"
    "Use <b>+</b> / <b>–</b> to show or hide the transcript. "
    "<b>Long record</b> records up to an hour and shows the text when you stop."
)

STYLE = """
QDialog { background: #F5F4ED; }
QLabel#sectionTitle { font-weight: 600; color: #3D3C38; margin-top: 4px; }
QLabel#fixedBinding { color: #5E5D59; }
QLabel#howTo { color: #3D3C38; background: #FFFFFF; border: 1px solid #E3E1D7; border-radius: 8px; padding: 10px; }
QComboBox { background: #FFFFFF; border: 1px solid #DAD8CD; border-radius: 6px; padding: 3px 8px; min-width: 210px; }
"""


class OptionsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MyTranscribe — Options")
        self.setStyleSheet(STYLE)
        self._original = settings
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        layout.addWidget(self._title("Start / stop dictation"))
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.key = self._combo([("none", "None")] + [(k, key_label(k)) for k in KEY_CHOICES], settings.key)
        self.key_mode = self._combo(MODES, settings.key_mode)
        self.mouse = self._combo([("none", "None")] + list(MOUSE_CHOICES.items()), settings.mouse)
        self.mouse_mode = self._combo(MODES, settings.mouse_mode)
        form.addRow("Keyboard key:", self.key)
        form.addRow("Key behaviour:", self.key_mode)
        form.addRow("Mouse button:", self.mouse)
        form.addRow("Mouse behaviour:", self.mouse_mode)
        for name, text in (("Ctrl+Alt+Q", "toggle, works anywhere (always on)"),
                           ("Space", "toggle, when the MyTranscribe window is focused")):
            lbl = QLabel(text)
            lbl.setObjectName("fixedBinding")
            form.addRow(f"{name}:", lbl)
        layout.addLayout(form)
        self.key.currentIndexChanged.connect(self._sync_enabled)
        self.mouse.currentIndexChanged.connect(self._sync_enabled)
        self._sync_enabled()

        layout.addWidget(self._title("View"))
        self.start_compact = QCheckBox("Start in compact view (button only)")
        self.start_compact.setChecked(settings.start_compact)
        layout.addWidget(self.start_compact)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E3E1D7;")
        layout.addWidget(line)
        how = QLabel(HOW_TO)
        how.setObjectName("howTo")
        how.setWordWrap(True)
        how.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(how)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.setMinimumWidth(460)

    @staticmethod
    def _title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    @staticmethod
    def _combo(items, current: str) -> QComboBox:
        c = QComboBox()
        for value, label in items:
            c.addItem(label, value)
        i = c.findData(current)
        c.setCurrentIndex(max(0, i))
        return c

    def _sync_enabled(self) -> None:
        self.key_mode.setEnabled(self.key.currentData() != "none")
        self.mouse_mode.setEnabled(self.mouse.currentData() != "none")

    def result_settings(self) -> Settings:
        """The edited settings (call after exec() returned Accepted)."""
        return replace(self._original, key=self.key.currentData(), key_mode=self.key_mode.currentData(),
                       mouse=self.mouse.currentData(), mouse_mode=self.mouse_mode.currentData(),
                       start_compact=self.start_compact.isChecked())
