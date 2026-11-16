"""log_window.py — a separate window showing the app's recent log (Options -> "Show log")."""

import os
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

import app_log

REFRESH_MS = 1000


class LogWindow(QWidget):
    """Read-only, follows new lines while scrolled to the bottom. Holds no transcript text."""

    def __init__(self, parent=None, handler=None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("MyTranscribe — Log")
        self.resize(820, 460)
        self._handler = handler or app_log.memory()
        self._shown = -1
        layout = QVBoxLayout(self)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.view)
        row = QHBoxLayout()
        note = QLabel(f"Timings and errors only, never what you dictated. Also saved in {app_log.log_file()}")
        note.setWordWrap(True)
        row.addWidget(note, 1)
        copy = QPushButton("Copy all")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.view.toPlainText()))
        row.addWidget(copy)
        folder = QPushButton("Open folder")
        folder.clicked.connect(self._open_folder)
        row.addWidget(folder)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        row.addWidget(close)
        layout.addLayout(row)
        self._timer = QTimer(self)
        self._timer.setInterval(REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self) -> None:
        if self._handler.count == self._shown:
            return
        self._shown = self._handler.count
        bar = self.view.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 2
        self.view.setPlainText(self._handler.text())
        if follow:
            bar.setValue(bar.maximum())

    @staticmethod
    def _open_folder() -> None:
        path = str(app_log.log_dir())
        try:
            if sys.platform == "win32":
                os.startfile(path)                                    # noqa: S606 (the user's own log folder)
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError:
            pass
