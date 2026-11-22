"""
setup_wizard.py — the setup wizard: first start, and Options → Run setup again.

Walks through the choices that matter most for a new user, one page each:

  1. Welcome            thanks, and how you dictate: traditional (you say the punctuation)
                        or natural speech. The one question without a preset answer on a
                        first start: the wrong answer costs more than anything else, so
                        "Use recommended for the rest" keeps it.
  2. This computer      graphics card, and the most accurate or the faster model
  3. Microphone         which one, a short level check, the gain
  4. Where the text goes  copy at Stop / paste at Stop / type while talking
  5. Start and stop     key and mouse button, hold or toggle, with a live test
  6. Summary            what will be saved (and what changed, on a re-run)

Pages 2–5 have the recommended answer already chosen.

It only edits a copy of settings.Settings; the caller saves and applies
result_settings(). Everything else (recogniser, language, medical clean-up,
pause-aware dictation) keeps its value and stays in Options. The plan for the
later phases (practice reading, tuning to the voice) is docs/settings/SETUP_WIZARD_PLAN.md.
"""

from dataclasses import replace
import threading
from typing import Callable, List, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QRadioButton, QSlider, QVBoxLayout, QWidget, QWizard, QWizardPage,
)

import audio_devices
import engines
from mic_check import CHECK_SENTENCE, QUIET_S, SPEAK_S, MicMonitor, analyse, meter_display
from options_dialog import MODES, STYLE, gain_text
from settings import Settings
from triggers import KEY_CHOICES, MOUSE_CHOICES, InputTriggers, TriggerConfig, key_label

SETUP_VERSION = 1

WIZARD_STYLE = STYLE + """
QWizard, QWizardPage, QWizard > QWidget > QFrame { background: #F5F4ED; }
QWizard > QWidget > QFrame { border: none; }
QRadioButton { color: #1F1E1D; spacing: 8px; font-weight: 600; background: transparent; }
QRadioButton::indicator { width: 14px; height: 14px; border-radius: 8px; background: #FFFFFF; border: 1px solid #77756D; }
QRadioButton::indicator:checked { background: #C96442; border: 1px solid #C96442; }
QRadioButton:disabled { color: #9C9A92; }
QLabel#pageText { color: #3D3C38; }
QLabel#sentence { color: #1F1E1D; background: #FFFFFF; border: 1px solid #E3E1D7; border-radius: 8px;
                  padding: 10px; font-size: 11pt; }
QLabel#checkStatus { color: #1F1E1D; font-weight: 600; }
QLabel#warning { color: #93370D; background: #FCEFE6; border: 1px solid #E9B48F; border-radius: 6px; padding: 6px 8px; }
QLabel#ok { color: #1F6E37; }
QLabel#triggerSeen { color: #1F6E37; font-weight: 600; }
QProgressBar#micLevel { background: #E3E1D7; border: none; border-radius: 3px; max-height: 8px; }
QProgressBar#micLevel::chunk { background: #2E9E4F; border-radius: 3px; }
QProgressBar#micLevel[levelKind="low"]::chunk { background: #B98500; }
QProgressBar#micLevel[levelKind="clipping"]::chunk { background: #C8322B; }
QFrame#choiceCard { background: #FFFFFF; border: 1px solid #E3E1D7; border-radius: 10px; }
QFrame#choiceCard:hover { border-color: #C9C7BD; }
QFrame#choiceCard[selected="true"] { background: #FCF3EE; border: 1px solid #C96442; }
QFrame#choiceCard:disabled { background: #F5F4ED; }
QLabel#eyebrow { color: #C96442; font-weight: 600; font-size: 8.5pt; letter-spacing: 1px; }
QLabel#heroTitle { color: #1F1E1D; font-size: 16pt; font-weight: 600; }
QLabel#heroText { color: #3D3C38; }
QPushButton:disabled { color: #A8A69E; background: #F0EEE6; border-color: #E3E1D7; }
QLabel#question { color: #1F1E1D; font-size: 12pt; font-weight: 600; margin-top: 10px; }
QLabel#example { color: #3D3C38; background: rgba(31, 30, 29, 0.05); border-radius: 6px; padding: 6px 10px; margin-left: 23px; }
QLabel#hint { color: #5E5D59; }
QCheckBox#inCard { font-weight: 400; margin-left: 23px; }
"""

# How you dictate (first page). Every statement here must be true of the app today:
# natural speech gets sentence punctuation from the recogniser and a letter's greeting and
# sign-off laid out (voice_commands.letter_layout), but no other paragraphs unless spoken
# (docs/settings/SETUP_WIZARD_PLAN.md, "Speaking naturally").
DICTATION = (
    ("traditional", "Traditional dictation",
     "You say the punctuation and the layout: “period”, “comma”, “new paragraph”."),
    ("natural", "Natural speech",
     "Talk as you would to a colleague. Full stops and commas are added from how you speak (saying "
     "“period” works too), and a letter's greeting and sign-off go on their own lines. For other "
     "paragraphs, say “new paragraph”."),
)
TRADITIONAL_EXAMPLE = (
    "<table cellspacing='0' cellpadding='1'>"
    "<tr><td style='color:#77756D; padding-right:10px'>You say</td>"
    "<td><i>“No fever comma no cough period”</i></td></tr>"
    "<tr><td style='color:#77756D; padding-right:10px'>You get</td><td>No fever, no cough.</td></tr></table>")
NEW_TO_DICTATION = ("New to dictating? Natural speech is the easier start; saying the punctuation gives "
                    "you more control over it. You can switch at any time in Options (⚙).")
DICTATION_SUMMARY = {"every": "traditional, every comma said", "some": "traditional",
                     "none": "natural speech"}
OUTPUT = (
    ("copy", "Copy the text when I stop, and I paste it with Ctrl+V",
     "You choose where it goes."),
    ("paste", "Paste the text where my cursor is when I stop",
     "The same text as copying, put in for you. Works when you stop with your key or mouse button; "
     "the on-screen Stop button only copies."),
    ("live", "Type into my document while I talk",
     "New text appears every few seconds. In testing it made slightly more word errors than copying at Stop "
     "(2.9% against 2.4% on 54 recordings), because each piece is written having heard less of the sentence. "
     "The full text is also copied when you stop. Keep the cursor in the same window while you dictate."),
)


# ── Pure helpers (unit-tested) ───────────────────────────────────────────────
def punctuation_choice(s: Settings) -> str:
    if s.dictation_style == "natural":
        return "none"
    if s.voice_commands and s.spoken_punctuation:
        return "every" if s.only_dictated_commas else "some"
    return "none"


def dictation_fields(choice: str) -> dict:
    """
    The settings an answer on the first page sets: 'every' / 'some' (traditional) or 'none' (natural).
    Spoken layout commands are on for both, because both cards tell the user to say "new paragraph".
    Spoken punctuation is on for natural speech too (2026-11-18): no worse on the owner's real
    recordings, better on the synthetic voices, and a natural speaker who does say "period" keeps
    the mark (docs/optimization/2026-11-18-settings-suite-fixes.md).
    """
    return dict(spoken_punctuation=True, only_dictated_commas=choice == "every", voice_commands=True,
                dictation_style="natural" if choice == "none" else "traditional")


def output_choice(s: Settings) -> str:
    return "live" if s.live_insert else "paste" if s.autopaste else "copy"


def describe_hardware(hw) -> tuple:
    """(text for the page, whether the Best / Fast choice applies) from a hw_profile.HardwareInfo."""
    from hw_profile import GPU_ACCURATE_MIN_VRAM_MB, GPU_SMALL_VRAM_THRESHOLD_MB
    if hw is None or not hw.cuda_device_count:
        return ("No NVIDIA graphics card was found, so dictation runs on the processor with a smaller "
                "model (small.en). The text comes a few seconds after you stop: in testing on laptop-class "
                "processor cores, about 2 seconds after a short message and 4 to 8 after a long one; "
                "an older or busy laptop takes longer. It makes more mistakes than on a graphics card, "
                "especially in drug names, so read the text before it goes into a record.", False)
    name = hw.gpu_name or "NVIDIA graphics card"
    size = f", {hw.vram_mb / 1024:.0f} GB" if hw.vram_mb else ""
    if hw.vram_mb is not None and hw.vram_mb < GPU_SMALL_VRAM_THRESHOLD_MB:
        return (f"Graphics card: {name}{size}. It has room for a smaller model (small.en), which is less "
                "accurate than the large ones.", False)
    if hw.vram_mb is not None and hw.vram_mb < GPU_ACCURATE_MIN_VRAM_MB:
        return (f"Graphics card: {name}{size}. It runs the fast model (large-v3-turbo); the most accurate "
                "model needs a card with 6 GB.", False)
    return (f"Graphics card: {name}{size}. It can run the most accurate model.", True)


def model_line(s: Settings, hw=None) -> str:
    """The model this PC will actually run, as the summary states it (hw: hw_profile.HardwareInfo, or None)."""
    from hw_profile import GPU_ACCURATE_MIN_VRAM_MB, GPU_SMALL_VRAM_THRESHOLD_MB
    if hw is not None and not hw.cuda_device_count:
        model = "small.en, on the processor (no NVIDIA graphics card)"
    elif hw is not None and hw.vram_mb is not None and hw.vram_mb < GPU_SMALL_VRAM_THRESHOLD_MB:
        model = "small.en (the graphics card has little memory)"
    elif hw is not None and hw.vram_mb is not None and hw.vram_mb < GPU_ACCURATE_MIN_VRAM_MB:
        model = "faster (large-v3-turbo)"
    else:
        model = "most accurate (large-v3)" if s.accuracy == "best" else "faster (large-v3-turbo)"
    extra = "" if s.engine == "whisper" else f", for Whisper; recogniser stays {engines.ENGINES[s.engine].label}"
    return f"Model: {model}{extra}"


def download_note(hw) -> str:
    """Where the speech model comes from on this PC: shipped with the installer, or asked for."""
    from hw_profile import CPU_DEFAULT_MODEL, GPU_ACCURATE_MODEL, GPU_DEFAULT_MODEL
    processor = hw is not None and not hw.cuda_device_count
    names = [CPU_DEFAULT_MODEL] if processor else [GPU_ACCURATE_MODEL, GPU_DEFAULT_MODEL]
    if any(engines.bundled_model(n) is not None for n in names):
        return "The speech model came with the installer: nothing is downloaded, and it works offline."
    size = "about 0.5 GB" if processor else "about 3 GB, or 1.6 GB for the faster model"
    note = (f"If the model is not on this PC yet, MyTranscribe asks before downloading it ({size}, once). "
            "After that it works offline.")
    if not processor and engines.fallback_model() is not None:
        note += (f" Until then, or if you say no, it uses the smaller model that came with the installer "
                 f"({CPU_DEFAULT_MODEL}).")
    return note


def summary_lines(s: Settings, device_label: str, hw=None) -> List[str]:
    out = {k: label for k, label, _ in OUTPUT}[output_choice(s)]
    triggers = s.triggers().describe()
    lines = [
        f"How you dictate: {DICTATION_SUMMARY[punctuation_choice(s)]}",
        model_line(s, hw),
        f"Microphone: {device_label}, gain {gain_text(s.mic_gain)}",
        "Spoken layout (“new paragraph”, “new line”, quotes): " + ("on" if s.voice_commands else "off"),
        f"Text: {out}",
        "Start and stop: " + ("; ".join(f"{a} ({b})" for a, b in triggers) or "on-screen button") +
        "; Ctrl+Alt+Q (toggle) always works",
    ]
    return lines


def changed_lines(before: Settings, after: Settings, device_label: str, before_device_label: str,
                  hw=None) -> List[str]:
    """The summary lines that differ, as 'old → new' (empty when nothing changed)."""
    a, b = summary_lines(before, before_device_label, hw), summary_lines(after, device_label, hw)
    out = []
    for old, new in zip(a, b):
        if old != new:
            head, _, new_value = new.partition(": ")
            out.append(f"{head}: {old.partition(': ')[2]} → {new_value}")
    return out


def light_palette(widget: QWidget) -> None:
    """The warm light theme of the Options screen, also when Windows is in dark mode (the wizard's
    page area takes its colours from the palette, not the style sheet)."""
    pal = widget.palette()
    for role, colour in ((QPalette.ColorRole.Window, "#F5F4ED"), (QPalette.ColorRole.Base, "#FFFFFF"),
                         (QPalette.ColorRole.WindowText, "#1F1E1D"), (QPalette.ColorRole.Text, "#1F1E1D"),
                         (QPalette.ColorRole.Button, "#FFFFFF"), (QPalette.ColorRole.ButtonText, "#1F1E1D"),
                         (QPalette.ColorRole.Highlight, "#F0D9CD"), (QPalette.ColorRole.HighlightedText, "#1F1E1D")):
        pal.setColor(role, QColor(colour))
    widget.setPalette(pal)


def _text(text: str, name: str = "pageText") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(name)
    lbl.setWordWrap(True)
    return lbl


def _help(text: str) -> QLabel:
    return _text(text, "optionHelp")


def _repolish(widget: QWidget) -> None:
    """Re-apply the style sheet after a property or object name used in it changed."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class ChoiceCard(QFrame):
    """One answer: its radio button and explanation in a card. Clicking anywhere on the card chooses it."""

    def __init__(self, key: str, label: str, help_text: str) -> None:
        super().__init__()
        self.setObjectName("choiceCard")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 10, 14, 10)
        self.body.setSpacing(3)
        self.button = QRadioButton(label)
        self.button.setProperty("choice", key)
        self.button.card = self
        self.button.help_label = _help(help_text)
        self.body.addWidget(self.button)
        self.body.addWidget(self.button.help_label)
        self.button.toggled.connect(self._show_selected)
        self._show_selected(False)

    def mousePressEvent(self, event) -> None:       # noqa: N802 (Qt name)
        if self.isEnabled():
            self.button.setChecked(True)
            self.button.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def _show_selected(self, on: bool) -> None:
        self.setProperty("selected", bool(on))
        _repolish(self)


def _radio_group(layout: QVBoxLayout, choices, current: str) -> QButtonGroup:
    group = QButtonGroup(layout)
    for i, (key, label, help_text) in enumerate(choices):
        card = ChoiceCard(key, label, help_text)
        card.button.setChecked(key == current)
        group.addButton(card.button, i)
        layout.addWidget(card)
    return group


def _checked(group: QButtonGroup) -> str:
    button = group.checkedButton()
    return button.property("choice") if button is not None else ""


# ── Microphone panel (wizard page and Options → Check my microphone) ─────────
class MicPanel(QWidget):
    """Microphone choice, live level, gain, and the guided check (mic_check.py)."""

    def __init__(self, device: str, gain: int, devices: Optional[List[str]] = None,
                 default_device: Optional[str] = None, open_stream: Optional[Callable] = None,
                 bluetooth: Optional[Callable[[str], bool]] = None, parent=None) -> None:
        super().__init__(parent)
        if devices is None or default_device is None:
            names, default = audio_devices.snapshot()
            devices = names if devices is None else devices
            default_device = default if default_device is None else default_device
        self._default_device = default_device
        self._bluetooth = bluetooth or (lambda name: audio_devices.is_bluetooth(name))
        self.monitor = MicMonitor(device, open_stream=open_stream, gain=gain)
        self.result = None
        self._phase = None
        self._phase_left = 0.0
        self._quiet = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        form = QFormLayout()
        self.device = QComboBox()
        self.device.addItem(f"Windows default ({default_device})" if default_device else "Windows default", "")
        for name in devices:
            self.device.addItem(name, name)
        if device and self.device.findData(device) < 0:
            self.device.addItem(f"{device} (not connected)", device)
        self.device.setCurrentIndex(max(0, self.device.findData(device)))
        self.device.currentIndexChanged.connect(self._device_changed)
        form.addRow("Microphone:", self.device)
        layout.addLayout(form)

        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Level:"))
        self.level = QProgressBar()
        self.level.setObjectName("micLevel")
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setAccessibleName("Microphone level")
        level_row.addWidget(self.level, stretch=1)
        layout.addLayout(level_row)

        gain_row = QHBoxLayout()
        gain_row.addWidget(QLabel("Gain:"))
        self.gain = QSlider(Qt.Orientation.Horizontal)
        self.gain.setRange(0, 100)
        self.gain.setValue(gain)
        self.gain.setAccessibleName("Microphone gain")
        self.gain_label = QLabel(gain_text(gain))
        self.gain_label.setObjectName("sliderValue")
        self.gain.valueChanged.connect(self._gain_changed)
        gain_row.addWidget(self.gain, stretch=1)
        gain_row.addWidget(self.gain_label)
        layout.addLayout(gain_row)

        check_row = QHBoxLayout()
        self.check_button = QPushButton("Check my microphone")
        self.check_button.clicked.connect(self._check_clicked)
        check_row.addWidget(self.check_button)
        check_row.addStretch(1)
        layout.addLayout(check_row)
        self.status = _text("Press Check my microphone: stay quiet for 3 seconds, then read one sentence aloud. "
                            "Nothing is saved or transcribed.", "checkStatus")
        layout.addWidget(self.status)
        self.sentence = _text(CHECK_SENTENCE, "sentence")
        self.sentence.setVisible(False)
        layout.addWidget(self.sentence)
        self.outcome = _text("", "ok")
        self.outcome.setVisible(False)
        layout.addWidget(self.outcome)
        self.warnings = QVBoxLayout()
        layout.addLayout(self.warnings)

        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)

    # public
    def selected_device(self) -> str:
        return self.device.currentData() or ""

    def device_label(self) -> str:
        return self.device.currentText()

    def start(self) -> None:
        self.monitor.device = self.selected_device()
        self.monitor.gain = self.gain.value()
        self.monitor.start()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self._phase = None
        self.monitor.stop()

    # internals
    def _device_changed(self) -> None:
        self._cancel_check()
        was_running = self._timer.isActive()
        self.monitor.stop()
        if was_running:
            self.start()

    def _gain_changed(self, value: int) -> None:
        self.gain_label.setText(gain_text(value))
        self.monitor.gain = value

    def _clear_warnings(self) -> None:
        while self.warnings.count():
            w = self.warnings.takeAt(0).widget()
            if w is not None:
                w.deleteLater()

    def _cancel_check(self) -> None:
        if self._phase is not None:
            self.monitor.end_recording()
        self._phase = None
        self.sentence.setVisible(False)
        self.check_button.setText("Check my microphone")

    def _check_clicked(self) -> None:
        if self._phase == "speak":            # "Finished reading"
            self._finish_check()
            return
        if self._phase is not None:
            return
        if not self.monitor.running:
            self.start()
        self.result = None
        self._clear_warnings()
        self.outcome.setVisible(False)
        self._phase, self._phase_left = "quiet", QUIET_S
        self.monitor.begin_recording()
        self.check_button.setEnabled(False)
        self._show_phase()

    def _show_phase(self) -> None:
        if self._phase == "quiet":
            self.status.setText(f"Stay quiet… {max(1, round(self._phase_left))}")
        elif self._phase == "speak":
            self.status.setText("Now read this aloud, at your usual dictating voice:")

    def _tick(self) -> None:
        value, kind = meter_display(self.monitor.level)
        self.level.setValue(value if self.monitor.running else 0)
        if self.level.property("levelKind") != kind:
            self.level.setProperty("levelKind", kind)
            self.level.style().unpolish(self.level)
            self.level.style().polish(self.level)
        if self.monitor.error and self._phase is None and not self.monitor.running:
            self.status.setText(self.monitor.error)
        if self._phase is None:
            return
        self._phase_left -= self._timer.interval() / 1000
        if self._phase == "quiet" and self._phase_left <= 0:
            self._quiet = self.monitor.end_recording()
            self._phase, self._phase_left = "speak", SPEAK_S
            self.monitor.begin_recording()
            self.sentence.setVisible(True)
            self.check_button.setText("Finished reading")
            self.check_button.setEnabled(True)
        elif self._phase == "speak" and self._phase_left <= 0:
            self._finish_check()
            return
        if not self.monitor.running and self.monitor.error:
            self._cancel_check()
            self.check_button.setEnabled(True)
            self.status.setText(self.monitor.error)
            return
        self._show_phase()

    def _finish_check(self) -> None:
        speech = self.monitor.end_recording()
        quiet = self._quiet
        self._quiet = None
        self._cancel_check()
        self.check_button.setEnabled(True)
        self.check_button.setText("Check again")
        if quiet is None or not quiet.size or not speech.size:
            self.status.setText(self.monitor.error or "No sound came from the microphone.")
            return
        self.result = analyse(quiet, speech, bluetooth=self._bluetooth(self.selected_device()
                                                                            or self._default_device or ""))
        self.gain.setValue(self.result.gain)
        self.status.setText("Done." if self.result.heard else "Check finished.")
        self.outcome.setText(self.result.summary())
        self.outcome.setObjectName("ok" if self.result.heard and not self.result.warnings else "pageText")
        self.outcome.style().unpolish(self.outcome)
        self.outcome.style().polish(self.outcome)
        self.outcome.setVisible(True)
        for text in self.result.warnings:
            self.warnings.addWidget(_text(text, "warning"))


class MicCheckDialog(QDialog):
    """Options → Check my microphone…: the microphone panel on its own."""

    def __init__(self, device: str, gain: int, parent=None, **panel_kwargs) -> None:
        super().__init__(parent)
        self.setWindowTitle("MyTranscribe — Check my microphone")
        light_palette(self)
        self.setStyleSheet(WIZARD_STYLE)
        layout = QVBoxLayout(self)
        self.panel = MicPanel(device, gain, **panel_kwargs)
        layout.addWidget(self.panel)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use these")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(560, 420)

    def showEvent(self, event) -> None:          # noqa: N802 (Qt name)
        super().showEvent(event)
        self.panel.start()

    def done(self, result: int) -> None:
        self.panel.stop()
        super().done(result)


# ── Pages ────────────────────────────────────────────────────────────────────
class WelcomePage(QWizardPage):
    """Thanks, and how you dictate. On a first start nothing is chosen until the user answers."""

    def __init__(self, settings: Settings, first_run: bool) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(_text("MYTRANSCRIBE MEDICAL", "eyebrow"))
        if first_run:
            layout.addWidget(_text("Thank you for choosing MyTranscribe", "heroTitle"))
            layout.addWidget(_text(
                "It turns what you say into text, here on this PC: nothing you dictate is sent anywhere. "
                "Setup takes about three minutes, and after this question the recommended answers are "
                "already chosen.", "heroText"))
        else:
            layout.addWidget(_text("Setup", "heroTitle"))
            layout.addWidget(_text(
                "Your current choices are filled in. Anything you change is listed before it is saved.",
                "heroText"))
        layout.addWidget(_text("How do you dictate?", "question"))
        current = punctuation_choice(settings)
        self.group = _radio_group(layout, DICTATION,
                                  "" if first_run else ("natural" if current == "none" else "traditional"))
        traditional = self.group.buttons()[0].card
        example = _text(TRADITIONAL_EXAMPLE, "example")
        example.setTextFormat(Qt.TextFormat.RichText)
        traditional.body.addWidget(example)
        self.every_comma = QCheckBox("I say every comma (leave out any I don't say)")
        self.every_comma.setObjectName("inCard")
        self.every_comma.setChecked(current == "every")
        traditional.body.addWidget(self.every_comma)
        layout.addWidget(_text(NEW_TO_DICTATION, "hint"))
        layout.addStretch(1)
        self.group.buttonToggled.connect(lambda *_: self._sync())
        self._sync()

    def _sync(self) -> None:
        self.every_comma.setVisible(_checked(self.group) == "traditional")
        self.completeChanged.emit()

    def isComplete(self) -> bool:                 # noqa: N802 (Qt name): Next waits for an answer
        return bool(_checked(self.group))

    def choice(self) -> str:
        """'every' / 'some' (traditional, with or without every comma) or 'none' (natural); '' if unanswered."""
        style = _checked(self.group)
        if style == "traditional":
            return "every" if self.every_comma.isChecked() else "some"
        return "none" if style == "natural" else ""


class ComputerPage(QWizardPage):
    def __init__(self, settings: Settings, hardware: Optional[Callable] = None) -> None:
        super().__init__()
        self.setTitle("This computer")
        self._hardware = hardware
        self._detected = False
        layout = QVBoxLayout(self)
        self.text = _text("Checking this computer…")
        layout.addWidget(self.text)
        self.group = _radio_group(layout, (
            ("best", "Most accurate (Whisper large-v3)", "Recommended. In testing on a 6 GB card (GTX 1660 Ti) the "
             "text came 1 to 1.5 seconds after Stop; an older card can take longer."),
            ("fast", "Faster (Whisper large-v3-turbo)", "Quicker on an older card, slightly less accurate.")),
            settings.accuracy)
        self._choice_widgets = [b.card for b in self.group.buttons()]
        self.download = _help(download_note(None))
        layout.addWidget(self.download)
        if settings.engine != "whisper":
            layout.addWidget(_help(f"The recogniser chosen in Options is {engines.ENGINES[settings.engine].label}; "
                                   "this choice applies when Whisper is used."))
        layout.addStretch(1)
        self._result = None

    def initializePage(self) -> None:      # noqa: N802 (Qt name)
        if self._detected:
            return
        self._detected = True
        for w in self._choice_widgets:
            w.setEnabled(False)

        def probe():
            try:
                if self._hardware is not None:
                    self._result = self._hardware()
                else:
                    from hw_profile import detect_hardware
                    self._result = detect_hardware()
            except Exception:
                self._result = None
            self._done = True

        self._done = False
        if self._hardware is not None:
            probe()
            self._show()
        else:
            threading.Thread(target=probe, name="hardware-probe", daemon=True).start()
            self._poll = QTimer(self)
            self._poll.setInterval(100)
            self._poll.timeout.connect(self._check_probe)
            self._poll.start()

    def _check_probe(self) -> None:
        if self._done:
            self._poll.stop()
            self._show()

    def _show(self) -> None:
        text, choice = describe_hardware(self._result)
        choice = choice and len(engines.accuracy_choices()) > 1     # an installed copy with one large model
        self.text.setText(text)
        for w in self._choice_widgets:
            w.setEnabled(choice)
            w.setVisible(choice)
        self.download.setText(download_note(self._result))

    def accuracy(self) -> str:
        choices = engines.accuracy_choices()
        checked = _checked(self.group) or "best"
        return checked if checked in choices else choices[0]

    def hardware(self):
        """What the page found (hw_profile.HardwareInfo), or None if it has not looked yet."""
        return self._result if self._detected and getattr(self, "_done", False) else None


class MicrophonePage(QWizardPage):
    def __init__(self, settings: Settings, **panel_kwargs) -> None:
        super().__init__()
        self.setTitle("Microphone")
        layout = QVBoxLayout(self)
        layout.addWidget(_text("Choose the microphone you dictate into and check its level. A headset microphone "
                               "close to your mouth gives the best text."))
        self.panel = MicPanel(settings.input_device, settings.mic_gain, **panel_kwargs)
        layout.addWidget(self.panel)
        layout.addStretch(1)

    def initializePage(self) -> None:      # noqa: N802 (Qt name)
        self.panel.start()

    def cleanupPage(self) -> None:         # noqa: N802 (Qt name): Back
        self.panel.stop()

    def validatePage(self) -> bool:        # noqa: N802 (Qt name): Next
        self.panel.stop()
        return True


class OutputPage(QWizardPage):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setTitle("Where the text goes")
        layout = QVBoxLayout(self)
        layout.addWidget(_text("When you dictate into a record or a letter, what should happen to the text?"))
        self.group = _radio_group(layout, OUTPUT, output_choice(settings))
        layout.addStretch(1)

    def choice(self) -> str:
        return _checked(self.group) or "copy"


class TriggersPage(QWizardPage):
    def __init__(self, settings: Settings, install_hooks: bool = True) -> None:
        super().__init__()
        self.setTitle("Start and stop")
        self._install_hooks = install_hooks
        self.triggers: Optional[InputTriggers] = None
        layout = QVBoxLayout(self)
        layout.addWidget(_text("Start and stop dictation without leaving the program you are typing in."))
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
        layout.addLayout(form)
        layout.addWidget(_help("Hold to talk: dictation runs while you hold it down. Toggle: press once to start "
                               "and again to stop. Ctrl+Alt+Q always toggles, and Space works when the "
                               "MyTranscribe window is in front. On many laptops the F keys work only with "
                               "the Fn key held: if yours does not register below, choose another key."))
        layout.addSpacing(6)
        self.seen = _text("Try it: press your key or mouse button now.", "pageText")
        layout.addWidget(self.seen)
        layout.addStretch(1)
        for combo in (self.key, self.key_mode, self.mouse, self.mouse_mode):
            combo.currentIndexChanged.connect(self._config_changed)
        self._sync_enabled()

    @staticmethod
    def _combo(items, current: str) -> QComboBox:
        c = QComboBox()
        for value, label in items:
            c.addItem(label, value)
        c.setCurrentIndex(max(0, c.findData(current)))
        return c

    def config(self) -> TriggerConfig:
        key, mouse = self.key.currentData(), self.mouse.currentData()
        return TriggerConfig(key=None if key == "none" else key, key_hold=self.key_mode.currentData() == "hold",
                             mouse=None if mouse == "none" else mouse,
                             mouse_hold=self.mouse_mode.currentData() == "hold")

    def _sync_enabled(self) -> None:
        self.key_mode.setEnabled(self.key.currentData() != "none")
        self.mouse_mode.setEnabled(self.mouse.currentData() != "none")

    def _config_changed(self) -> None:
        self._sync_enabled()
        if self.triggers is not None:
            self._start_listening()

    def _label(self, source: str) -> str:
        cfg = self.triggers.config if self.triggers is not None else self.config()
        return key_label(cfg.key) if source == "key" else MOUSE_CHOICES.get(cfg.mouse or "", "Mouse button")

    def _pressed(self, source: str) -> None:
        cfg = self.triggers.config
        how = "hold it to keep dictating" if cfg.hold_for(source) else "press again to stop"
        self.seen.setObjectName("triggerSeen")
        self.seen.setText(f"✓ {self._label(source)} works: it starts dictation ({how}).")
        self.seen.style().unpolish(self.seen)
        self.seen.style().polish(self.seen)

    def _released(self, source: str) -> None:
        if self.triggers.config.hold_for(source):
            self.seen.setText(f"✓ {self._label(source)} works: hold to talk, and letting go stops dictation.")

    def _start_listening(self) -> None:
        self._stop_listening()
        self.triggers = InputTriggers(self.config(), parent=self)
        self.triggers.pressed.connect(self._pressed, Qt.ConnectionType.QueuedConnection)
        self.triggers.released.connect(self._released, Qt.ConnectionType.QueuedConnection)
        if self._install_hooks:
            try:
                self.triggers.start()
            except Exception:
                self.seen.setText("The key and mouse test is not available here; your choice is still saved.")

    def _stop_listening(self) -> None:
        if self.triggers is not None:
            try:
                self.triggers.stop()
            except Exception:
                pass
            self.triggers.deleteLater()
            self.triggers = None

    def initializePage(self) -> None:      # noqa: N802 (Qt name)
        self._start_listening()

    def cleanupPage(self) -> None:         # noqa: N802 (Qt name)
        self._stop_listening()

    def validatePage(self) -> bool:        # noqa: N802 (Qt name)
        self._stop_listening()
        return True


class SummaryPage(QWizardPage):
    def __init__(self, wizard: "SetupWizard") -> None:
        super().__init__()
        self._wizard = wizard
        self.setTitle("Ready")
        layout = QVBoxLayout(self)
        self.lines = _text("")
        self.lines.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.lines)
        self.changes = _text("")
        self.changes.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.changes)
        layout.addWidget(_help("Finish saves these. Each one can be changed later in Options (⚙), where you can also "
                               "run this setup again."))
        layout.addStretch(1)

    def initializePage(self) -> None:      # noqa: N802 (Qt name)
        w = self._wizard
        new = w.result_settings()
        import html
        hw = w.computer.hardware()
        items = "".join(f"<li>{html.escape(x)}</li>" for x in summary_lines(new, w.device_label(), hw))
        self.lines.setText(f"<b>These will be saved:</b><ul style='margin-left:-20px'>{items}</ul>")
        if w.first_run:
            self.changes.setVisible(False)
            return
        changed = changed_lines(w.original, new, w.device_label(), w.original_device_label, hw)
        self.changes.setVisible(True)
        self.changes.setText("<b>Changed from before:</b><ul style='margin-left:-20px'>"
                             + "".join(f"<li>{html.escape(x)}</li>" for x in changed) + "</ul>"
                             if changed else "Nothing changed from your current settings.")


# ── The wizard ───────────────────────────────────────────────────────────────
class _SoftRuler(QObject):
    """Paints the wizard's line above the buttons in the page's border colour instead of black."""

    def eventFilter(self, obj, event) -> bool:      # noqa: N802 (Qt name)
        if event.type() != QEvent.Type.Paint:
            return False
        p = QPainter(obj)
        p.fillRect(obj.rect(), QColor("#F5F4ED"))
        p.fillRect(0, 0, obj.width(), 1, QColor("#E3E1D7"))
        p.end()
        return True


class SetupWizard(QWizard):
    def __init__(self, settings: Settings, parent=None, first_run: bool = False,
                 hardware: Optional[Callable] = None, devices: Optional[List[str]] = None,
                 default_device: Optional[str] = None, open_stream: Optional[Callable] = None,
                 bluetooth: Optional[Callable[[str], bool]] = None, install_hooks: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("MyTranscribe — Setup")
        light_palette(self)
        self.setStyleSheet(WIZARD_STYLE)
        self.setWizardStyle(QWizard.WizardStyle.ClassicStyle)   # the modern header ignores the light theme
        self._soft_ruler = _SoftRuler(self)
        for ruler in self.findChildren(QWidget):     # Qt's line above the buttons: a bare 2-pixel QWidget
            if ruler.metaObject().className() == "QWidget" and ruler.minimumHeight() == ruler.maximumHeight() == 2:
                ruler.installEventFilter(self._soft_ruler)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.HaveCustomButton1, first_run)
        self.setButtonText(QWizard.WizardButton.CustomButton1, "Use recommended for the rest")
        self.customButtonClicked.connect(self._use_recommended)
        self.original = settings
        self.first_run = first_run
        self._recommended = False
        if devices is None or default_device is None:
            names, default = audio_devices.snapshot()
            devices = names if devices is None else devices
            default_device = default if default_device is None else default_device
        self.original_device_label = (settings.input_device or
                                      (f"Windows default ({default_device})" if default_device else "Windows default"))
        self.welcome = WelcomePage(settings, first_run)
        self.computer = ComputerPage(settings, hardware)
        self.microphone = MicrophonePage(settings, devices=devices, default_device=default_device,
                                         open_stream=open_stream, bluetooth=bluetooth)
        self.output = OutputPage(settings)
        self.trigger_page = TriggersPage(settings, install_hooks=install_hooks)
        self.summary = SummaryPage(self)
        for page in (self.welcome, self.computer, self.microphone, self.output, self.trigger_page, self.summary):
            self.addPage(page)
        self.currentIdChanged.connect(self._page_changed)
        self.welcome.completeChanged.connect(self._sync_recommended)
        self._page_changed(self.startId())
        self._sync_recommended()
        self.resize(660, 640)

    def _page_changed(self, page_id: int) -> None:
        buttons = [QWizard.WizardButton.Stretch]
        if self.first_run and page_id == self.startId():
            buttons.append(QWizard.WizardButton.CustomButton1)
        buttons += [QWizard.WizardButton.BackButton, QWizard.WizardButton.NextButton,
                    QWizard.WizardButton.FinishButton, QWizard.WizardButton.CancelButton]
        self.setButtonLayout(buttons)

    def _sync_recommended(self) -> None:
        self.button(QWizard.WizardButton.CustomButton1).setEnabled(self.welcome.isComplete())

    def _use_recommended(self, which: int) -> None:
        if not self.welcome.isComplete():
            return
        self._recommended = True
        self.accept()

    def device_label(self) -> str:
        return self.microphone.panel.device_label()

    def result_settings(self) -> Settings:
        """The settings to save (call after exec() returned Accepted)."""
        punct = self.welcome.choice() or "none"
        if self._recommended:
            return replace(Settings(), setup_version=SETUP_VERSION, **dictation_fields(punct))
        out = self.output.choice()
        triggers = self.trigger_page.config()
        return replace(
            self.original,
            accuracy=self.computer.accuracy(),
            input_device=self.microphone.panel.selected_device(),
            mic_gain=self.microphone.panel.gain.value(),
            **dictation_fields(punct),
            autopaste=out == "paste",
            live_insert=out == "live",
            key=triggers.key or "none", key_mode=self.trigger_page.key_mode.currentData(),
            mouse=triggers.mouse or "none", mouse_mode=self.trigger_page.mouse_mode.currentData(),
            setup_version=SETUP_VERSION,
        ).clean()

    def done(self, result: int) -> None:
        self.microphone.panel.stop()
        self.trigger_page._stop_listening()
        super().done(result)
