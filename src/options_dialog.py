"""
options_dialog.py — the Options screen for gui_med.py.

Shows which keys start/stop dictation, lets the user change the single key,
the mouse button and hold-to-talk vs toggle for each, the start-up view, and
gives a short how-to. Returns an edited copy of settings.Settings; the caller
saves and applies it. New options belong here, not on the main window.
"""

from dataclasses import replace
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QLabel, QScrollArea, QVBoxLayout, QWidget, QSlider, QHBoxLayout,
)

from settings import Settings
from triggers import KEY_CHOICES, MOUSE_CHOICES, key_label

MODES = [("hold", "Hold to talk"), ("toggle", "Toggle (press to start, press to stop)")]
ACCURACY = [("best", "Best — large-v3 (prioritize accuracy)"),
            ("fast", "Fast — large-v3-turbo (prioritize speed)")]

HOW_TO = (
    "<b>How it works</b><br>"
    "Dictate, stop, then wait for <b>Copied</b> and paste with <b>Ctrl+V</b>. "
    "Transcription stays on this PC.<br><br>"
    "Light: <b><span style='color:#2E9E4F'>green = recording</span></b>, "
    "<b><span style='color:#C8322B'>red = stopped</span></b>, amber = mic opening. "
    "Start talking on green.<br>"
    "Level bar: captured input; amber = low, red = too loud. No automatic gain.<br>"
    "Longer speech uses 30-second pieces; short snippets are sent immediately on Stop. "
    "Record for up to an hour.<br>"
    "<b>Not copied?</b> Click Copy and try again. <b>+</b> shows the transcript. "
    "Always review medical terms and numbers."
)

STYLE = """
QDialog, QScrollArea, QScrollArea > QWidget > QWidget { background: #F5F4ED; }
QLabel, QCheckBox { color: #1F1E1D; background: transparent; }
QComboBox, QComboBox QAbstractItemView { color: #1F1E1D; background: #FFFFFF; selection-background-color: #F0D9CD; selection-color: #1F1E1D; }
QPushButton { background: #FFFFFF; color: #1F1E1D; border: 1px solid #DAD8CD; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #ECEADF; }
QCheckBox::indicator { width: 14px; height: 14px; background: #FFFFFF; border: 1px solid #77756D; border-radius: 3px; }
QCheckBox::indicator:checked { background: #C96442; border: 3px solid #F0D9CD; }
QSlider::groove:horizontal { background: #DAD8CD; height: 5px; }
QSlider::sub-page:horizontal { background: #C96442; }
QSlider::handle:horizontal { background: #C96442; width: 16px; margin: -5px 0; border-radius: 8px; }
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
        outer = QVBoxLayout(self)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)

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

        layout.addWidget(self._title("Start / stop sounds"))
        sound_row = QHBoxLayout()
        self.chime_volume = QSlider(Qt.Orientation.Horizontal)
        self.chime_volume.setRange(0, 100)
        self.chime_volume.setValue(settings.chime_volume)
        self.chime_volume.setAccessibleName("Start and stop sound volume")
        volume_label = QLabel()
        def show_volume(value):
            volume_label.setText("Muted" if value == 0 else f"{value}%")
        self.chime_volume.valueChanged.connect(show_volume)
        show_volume(settings.chime_volume)
        sound_row.addWidget(self.chime_volume)
        sound_row.addWidget(volume_label)
        layout.addLayout(sound_row)

        layout.addWidget(self._title("Speech model"))
        acc_form = QFormLayout()
        acc_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.accuracy = self._combo(ACCURACY, settings.accuracy)
        acc_form.addRow("Accuracy:", self.accuracy)
        note = QLabel("Takes effect next time MyTranscribe starts.")
        note.setObjectName("fixedBinding")
        acc_form.addRow("", note)
        layout.addLayout(acc_form)

        layout.addWidget(self._title("Microphone"))
        self.keep_mic_ready = QCheckBox("Keep microphone ready (avoid clipped first words)")
        self.keep_mic_ready.setToolTip("Windows shows the microphone in use while MyTranscribe is open. "
                                      "Audio is kept in memory; idle audio is not transcribed.")
        self.keep_mic_ready.setChecked(settings.keep_mic_ready)
        layout.addWidget(self.keep_mic_ready)

        layout.addWidget(self._title("Text"))
        self.autopaste = QCheckBox("Paste automatically after stopping dictation")
        self.autopaste.setToolTip("Stop with a hotkey to paste into the focused field. The on-screen Stop button only copies.")
        self.autopaste.setChecked(settings.autopaste)
        if "MYTRANSCRIBE_AUTOPASTE" in os.environ:
            self.autopaste.setEnabled(False)
            self.autopaste.setToolTip("MYTRANSCRIBE_AUTOPASTE currently overrides this setting. Remove that environment variable to use this option.")
        layout.addWidget(self.autopaste)
        self.voice_commands = QCheckBox("Spoken formatting: new line, paragraph, quotes")
        self.voice_commands.setToolTip("Say “new line”, “new paragraph” or “open quote … close quote”.")
        self.voice_commands.setChecked(settings.voice_commands)
        layout.addWidget(self.voice_commands)
        self.live_insert = QCheckBox("Insert finished pieces at cursor (about 30 seconds)")
        self.live_insert.setToolTip("Each finished piece is inserted while you dictate. "
                                   "The full text is also copied when you stop.")
        self.live_insert.setChecked(settings.live_insert)
        layout.addWidget(self.live_insert)

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
        outer.addWidget(buttons)
        self.setMinimumWidth(460)
        screen = QApplication.primaryScreen()
        available_height = screen.availableGeometry().height() if screen else 900
        self.resize(560, min(760, max(300, available_height - 80)))

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
                       start_compact=self.start_compact.isChecked(), accuracy=self.accuracy.currentData(),
                       voice_commands=self.voice_commands.isChecked(),
                       keep_mic_ready=self.keep_mic_ready.isChecked(),
                       live_insert=self.live_insert.isChecked(),
                       chime_volume=self.chime_volume.value(), autopaste=self.autopaste.isChecked())
