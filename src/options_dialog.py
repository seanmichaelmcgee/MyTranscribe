"""
options_dialog.py — the Options screen for gui_med.py.

Start/stop keys and mouse button (hold-to-talk or toggle), microphone gain,
start/stop sounds, speech model and dictation language, the text options
(each with a one-line explanation under it), the start-up view, a short how-to
and the log. Returns an edited copy of settings.Settings; the caller saves and
applies it. New options belong here, not on the main window.
"""

from dataclasses import replace
import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget, QSlider, QHBoxLayout,
)

import engines
import lang_packs
from chunked_transcriber import GAIN_DB_PER_STEP
from settings import Settings
from triggers import KEY_CHOICES, MOUSE_CHOICES, key_label

MODES = [("hold", "Hold to talk"), ("toggle", "Toggle (press to start, press to stop)")]
ACCURACY = [("best", "Best: large-v3 (most accurate)"),
            ("fast", "Fast: large-v3-turbo (quicker, slightly less accurate)")]
# Dictation languages offered in Options. Spanish and French are marked experimental;
# Swahili is not offered until it has been validated (MYTRANSCRIBE_LANGUAGE=sw still works).
SHOWN_LANGUAGES = ("en", "es", "fr")
EXPERIMENTAL_LANGUAGES = ("es", "fr", "sw")

HOW_TO = (
    "<b>How it works</b><br>"
    "Dictate, stop, then wait for <b>Copied</b> and paste with <b>Ctrl+V</b>. "
    "Everything stays on this PC: nothing you dictate is sent anywhere.<br><br>"
    "Light: <b><span style='color:#2E9E4F'>green = recording</span></b>, "
    "<b><span style='color:#C8322B'>red = stopped</span></b>, amber = microphone starting. "
    "Start talking on green.<br>"
    "Level bar (above the Start button): green while you speak is right; amber = too quiet, "
    "red = too loud. Adjust with Microphone gain above.<br>"
    "Speech is transcribed in pieces of about 30 seconds while you talk; the rest is done when you stop. "
    "One recording can last up to an hour.<br>"
    "<b>Not copied?</b> Click Copy and try again. <b>+</b> shows the transcript, <b>–</b> hides it. "
    "Words highlighted in the transcript are worth checking.<br><br>"
    "<b>Always read the text before it goes into a record</b>, especially drug names, doses and numbers."
)

_CHECK_SVG = (Path(__file__).parent / "assets" / "check.svg").as_posix()

STYLE = """
QDialog, QScrollArea, QScrollArea > QWidget > QWidget { background: #F5F4ED; }
QLabel, QCheckBox { color: #1F1E1D; background: transparent; }
QComboBox, QComboBox QAbstractItemView { color: #1F1E1D; background: #FFFFFF; selection-background-color: #F0D9CD; selection-color: #1F1E1D; }
QPushButton { background: #FFFFFF; color: #1F1E1D; border: 1px solid #DAD8CD; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #ECEADF; }
QCheckBox { spacing: 8px; font-weight: 600; }
QCheckBox:disabled { color: #9C9A92; }
QCheckBox::indicator { width: 14px; height: 14px; background: #FFFFFF; border: 1px solid #77756D; border-radius: 3px; }
QCheckBox::indicator:checked { background: #C96442; border: 1px solid #C96442; image: url(%CHECK%); }
QCheckBox::indicator:disabled { background: #ECEADF; border-color: #C9C7BD; }
QCheckBox::indicator:checked:disabled { background: #E6CDC1; border-color: #E6CDC1; }
QSlider::groove:horizontal { background: #DAD8CD; height: 5px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #C96442; border-radius: 2px; }
QSlider::handle:horizontal { background: #C96442; width: 16px; margin: -6px 0; border-radius: 8px; }
QLabel#sectionTitle { font-weight: 600; font-size: 10.5pt; color: #3D3C38; margin-top: 8px; }
QLabel#fixedBinding { color: #5E5D59; }
QLabel#optionHelp { color: #5E5D59; margin-left: 23px; margin-bottom: 4px; }
QLabel#optionHelp:disabled { color: #9C9A92; }
QLabel#sliderValue { color: #3D3C38; min-width: 92px; }
QLabel#howTo { color: #3D3C38; background: #FFFFFF; border: 1px solid #E3E1D7; border-radius: 8px; padding: 10px; }
QComboBox { background: #FFFFFF; border: 1px solid #DAD8CD; border-radius: 6px; padding: 3px 8px; min-width: 210px; }
""".replace("%CHECK%", _CHECK_SVG)


def gain_text(value: int) -> str:
    """Microphone gain slider value as shown next to it: '50 · unchanged', '70 · +8 dB'."""
    db = (value - 50) * GAIN_DB_PER_STEP
    if abs(db) < 0.05:
        return f"{value} · unchanged"
    return f"{value} · {'+' if db > 0 else '−'}{abs(db):.0f} dB"


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
        layout.setSpacing(6)
        self._layout = layout
        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)

        # ── Start / stop ─────────────────────────────────────────────────────
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

        # ── Microphone ───────────────────────────────────────────────────────
        layout.addWidget(self._title("Microphone"))
        self.mic_gain, gain_label = self._slider(settings.mic_gain, "Microphone gain", gain_text)
        gain_row = QHBoxLayout()
        gain_name = QLabel("Gain:")
        gain_row.addWidget(gain_name)
        gain_row.addWidget(self.mic_gain, stretch=1)
        gain_row.addWidget(gain_label)
        layout.addLayout(gain_row)
        self._help("50 leaves the sound as the microphone sends it. Dictate a sentence and watch the level bar "
                   "above the Start button: it should be green and move while you speak. Mostly amber: raise "
                   "the gain. Red: lower it or move the microphone back. A very quiet microphone is best "
                   "raised first in Windows (Settings → System → Sound → Input).", indent=False)
        self.keep_mic_ready = self._option(
            "Keep microphone ready", settings.keep_mic_ready,
            "Keeps the microphone open between dictations so your first words are not clipped. "
            "Windows shows the microphone as in use while MyTranscribe is open; audio between "
            "dictations is held briefly in memory and never transcribed.")

        # ── Sounds ───────────────────────────────────────────────────────────
        layout.addWidget(self._title("Start / stop sounds"))
        self.chime_volume, volume_label = self._slider(
            settings.chime_volume, "Start and stop sound volume", lambda v: "Muted" if v == 0 else f"{v}%")
        sound_row = QHBoxLayout()
        sound_row.addWidget(QLabel("Volume:"))
        sound_row.addWidget(self.chime_volume, stretch=1)
        sound_row.addWidget(volume_label)
        layout.addLayout(sound_row)

        # ── Speech model ─────────────────────────────────────────────────────
        layout.addWidget(self._title("Speech model"))
        acc_form = QFormLayout()
        acc_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.engine = QComboBox()
        offered = list(engines.OFFERED)
        if settings.engine not in offered and settings.engine in engines.ENGINES:
            offered.append(settings.engine)          # a trial engine chosen by environment variable
        for name in offered:
            info = engines.ENGINES[name]
            ok, why = engines.availability(name)
            self.engine.addItem(info.label if ok else f"{info.label} — {why}", name)
            if not ok and name != settings.engine:
                item = self.engine.model().item(self.engine.count() - 1)
                item.setEnabled(False)
        self.engine.setCurrentIndex(max(0, self.engine.findData(settings.engine)))
        acc_form.addRow("Recogniser:", self.engine)
        self.accuracy = self._combo(ACCURACY, settings.accuracy)
        acc_form.addRow("Accuracy:", self.accuracy)
        languages = [(code, name + (" (experimental)" if code in EXPERIMENTAL_LANGUAGES else ""))
                     for code, name in lang_packs.LANGUAGES
                     if code in SHOWN_LANGUAGES or code == settings.language]
        self.language = self._combo(languages, settings.language)
        acc_form.addRow("Dictation language:", self.language)
        self.language.currentIndexChanged.connect(self._sync_engine)
        self.engine_note = QLabel()
        self.engine_note.setObjectName("fixedBinding")
        self.engine_note.setWordWrap(True)
        acc_form.addRow("", self.engine_note)
        layout.addLayout(acc_form)
        self.engine.currentIndexChanged.connect(self._sync_engine)
        self._sync_engine()

        # ── Text ─────────────────────────────────────────────────────────────
        layout.addWidget(self._title("Text"))
        self.pause_aware = self._option(
            "Pause-aware dictation", settings.pause_aware,
            "Keeps a sentence together when you pause to think, puts back a spoken “new paragraph” "
            "the model skipped, and listens a moment after you stop so the last word is not cut off.")
        self.voice_commands = self._option(
            "Spoken formatting", settings.voice_commands,
            "Say “new line”, “new paragraph”, or “open quote … close quote”.")
        self.spoken_punctuation = self._option(
            "Spoken punctuation", settings.spoken_punctuation,
            "For people who say the marks: “period”, “comma”, “colon”, “question mark”, “open/close "
            "parenthesis” become the marks. “Her last period” and “the sigmoid colon” stay words. "
            "Leave off if you do not dictate punctuation.")
        self.only_dictated_commas = self._option(
            "Only the commas I dictate", settings.only_dictated_commas,
            "With spoken punctuation: commas the model adds by itself are removed and only the ones "
            "you say are kept. For people who dictate every comma.")
        self.extra_fixes = self._option(
            "Medical clean-up", settings.extra_fixes,
            "Writes readings the chart way (138/78, 124 g/L, 37.2 °C, 5 mg/day), turns a misheard drug name "
            "into the real drug it sounds like when it sits where a drug belongs (before a dose, in a "
            "medication list), and capitalises brand names. Never invents a drug: check drug names as always.")
        self.spoken_punctuation.setEnabled(settings.voice_commands)
        self.voice_commands.toggled.connect(self._sync_text_options)
        self.spoken_punctuation.toggled.connect(self._sync_text_options)
        self._sync_text_options()

        # ── Output ───────────────────────────────────────────────────────────
        layout.addWidget(self._title("Where the text goes"))
        self.autopaste = self._option(
            "Paste automatically after stopping", settings.autopaste,
            "When you stop with the key or mouse button, the text is pasted into the field you were "
            "typing in. The on-screen Stop button only copies.")
        if "MYTRANSCRIBE_AUTOPASTE" in os.environ:
            self.autopaste.setEnabled(False)
            self.autopaste.setToolTip("MYTRANSCRIBE_AUTOPASTE currently overrides this setting. "
                                      "Remove that environment variable to use this option.")
        self.live_insert = self._option(
            "Type into my document while I dictate", settings.live_insert,
            "Each finished piece (about every 30 seconds) is pasted at the cursor while you keep talking. "
            "The full text is also copied when you stop. Keep the cursor in the same window.")

        # ── View ─────────────────────────────────────────────────────────────
        layout.addWidget(self._title("View"))
        self.start_compact = self._option(
            "Start in compact view", settings.start_compact,
            "Opens with the button only; + shows the transcript.")

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E3E1D7;")
        layout.addSpacing(6)
        layout.addWidget(line)
        how = QLabel(HOW_TO)
        how.setObjectName("howTo")
        how.setWordWrap(True)
        how.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(how)

        layout.addWidget(self._title("Troubleshooting"))
        self.log_window = None
        self.show_log = QPushButton("Show log…")
        self.show_log.setToolTip("Opens the recent log in its own window: timings and errors, never what you dictated.")
        self.show_log.clicked.connect(self._show_log)
        log_row = QHBoxLayout()
        log_row.addWidget(self.show_log)
        log_row.addStretch(1)
        layout.addLayout(log_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.setMinimumWidth(480)
        screen = QApplication.primaryScreen()
        available_height = screen.availableGeometry().height() if screen else 900
        self.resize(580, min(800, max(300, available_height - 80)))

    # ── building blocks ──────────────────────────────────────────────────────
    @staticmethod
    def _title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    def _help(self, text: str, indent: bool = True) -> QLabel:
        """A grey explanation line under an option, always visible (tooltips are easy to miss)."""
        lbl = QLabel(text)
        lbl.setObjectName("optionHelp")
        lbl.setWordWrap(True)
        if not indent:
            lbl.setStyleSheet("margin-left: 0px;")
        self._layout.addWidget(lbl)
        return lbl

    def _option(self, text: str, checked: bool, help_text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.setChecked(checked)
        box.setToolTip(help_text)
        self._layout.addWidget(box)
        box.help_label = self._help(help_text)
        return box

    @staticmethod
    def _slider(value: int, name: str, describe):
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(value)
        slider.setAccessibleName(name)
        label = QLabel()
        label.setObjectName("sliderValue")
        slider.valueChanged.connect(lambda v: label.setText(describe(v)))
        label.setText(describe(value))
        return slider, label

    @staticmethod
    def _combo(items, current: str) -> QComboBox:
        c = QComboBox()
        for value, label in items:
            c.addItem(label, value)
        i = c.findData(current)
        c.setCurrentIndex(max(0, i))
        return c

    def _sync_text_options(self) -> None:
        """Spoken punctuation needs spoken formatting; dictated-commas-only needs both."""
        commands = self.voice_commands.isChecked()
        self.spoken_punctuation.setEnabled(commands)
        self.spoken_punctuation.help_label.setEnabled(commands)
        commas = commands and self.spoken_punctuation.isChecked()
        self.only_dictated_commas.setEnabled(commas)
        self.only_dictated_commas.help_label.setEnabled(commas)

    def _sync_engine(self) -> None:
        """Accuracy only applies to Whisper; say what the chosen model is and where it comes from."""
        name = self.engine.currentData()
        info = engines.ENGINES[name]
        self.accuracy.setEnabled(name == "whisper")
        note = (f"{info.note} Download: {info.size}. Licence: {info.licence}. "
                "Saving a change reloads the model; you are asked before any download.")
        pack = lang_packs.get(self.language.currentData())
        if pack is not None:
            note += (f" {pack.name} is experimental: spoken commands and punctuation use that language's words, "
                     f"and the English medical vocabulary and spelling correction are off. {pack.reviewed}")
            if name != "whisper":
                note += " Only Whisper understands this language: choose Whisper as the recogniser."
            elif engines.tuned_model(pack.code) is not None:
                note += " A model tuned for this language is installed and will be used."
            elif pack.needs_tuned_model:
                note += (" Standard Whisper is weak in this language: install the tuned model with "
                         "scripts\\convert_whisper_model.py (see the multilingual note).")
        self.engine_note.setText(note)

    def _show_log(self) -> None:
        from log_window import LogWindow
        if self.log_window is None:
            self.log_window = LogWindow(parent=self)      # a child of this dialog, so it stays usable
        self.log_window.show()
        self.log_window.raise_()

    def _sync_enabled(self) -> None:
        self.key_mode.setEnabled(self.key.currentData() != "none")
        self.mouse_mode.setEnabled(self.mouse.currentData() != "none")

    def result_settings(self) -> Settings:
        """The edited settings (call after exec() returned Accepted)."""
        return replace(self._original, key=self.key.currentData(), key_mode=self.key_mode.currentData(),
                       mouse=self.mouse.currentData(), mouse_mode=self.mouse_mode.currentData(),
                       start_compact=self.start_compact.isChecked(), accuracy=self.accuracy.currentData(),
                       engine=self.engine.currentData(), language=self.language.currentData(),
                       voice_commands=self.voice_commands.isChecked(),
                       keep_mic_ready=self.keep_mic_ready.isChecked(),
                       live_insert=self.live_insert.isChecked(),
                       pause_aware=self.pause_aware.isChecked(),
                       spoken_punctuation=self.spoken_punctuation.isChecked(),
                       only_dictated_commas=self.only_dictated_commas.isChecked(),
                       extra_fixes=self.extra_fixes.isChecked(),
                       mic_gain=self.mic_gain.value(),
                       chime_volume=self.chime_volume.value(), autopaste=self.autopaste.isChecked())
