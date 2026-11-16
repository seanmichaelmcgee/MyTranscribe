"""
app_log.py — logging that works without a console window.

The app can be started with pythonw.exe (no PowerShell/console window). Then
there is nowhere to print to, so messages go to:

  * a small file that rotates:  %LOCALAPPDATA%\\MyTranscribe\\mytranscribe.log
  * the last few hundred lines in memory, shown by Options -> "Show log".

Same content as the console log always had: timings, lengths and errors,
never transcript text.
"""

import collections
import logging
import logging.handlers
import os
import sys
from pathlib import Path

FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"
MEMORY_LINES = 800
_memory = None


class MemoryHandler(logging.Handler):
    """Keeps the most recent formatted lines."""

    def __init__(self, capacity: int = MEMORY_LINES) -> None:
        super().__init__()
        self.lines = collections.deque(maxlen=capacity)
        self.count = 0                       # total lines ever seen (for cheap change detection)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
            self.count += 1
        except Exception:
            pass

    def text(self) -> str:
        return "\n".join(self.lines)


def log_dir(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("LOCALAPPDATA") or env.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "MyTranscribe"


def log_file(env=None) -> Path:
    return log_dir(env) / "mytranscribe.log"


def memory() -> MemoryHandler:
    """The in-memory handler (created by setup(); a detached one before that)."""
    global _memory
    if _memory is None:
        _memory = MemoryHandler()
        _memory.setFormatter(logging.Formatter(FORMAT))
    return _memory


def setup(to_file: bool = True, env=None) -> None:
    """Configure the root logger once: console if there is one, memory, and the file."""
    # pythonw.exe has no stdout/stderr; libraries that print (download progress) must not crash.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    elif hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(FORMAT)
    handlers = []
    if not any(isinstance(h, MemoryHandler) for h in root.handlers):
        handlers.append(memory())
        if getattr(sys.stdout, "name", "") != os.devnull:
            handlers.append(logging.StreamHandler(sys.stdout))
    if to_file and not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        try:
            log_dir(env).mkdir(parents=True, exist_ok=True)
            handlers.append(logging.handlers.RotatingFileHandler(
                log_file(env), maxBytes=1_000_000, backupCount=2, encoding="utf-8"))
        except OSError:
            pass                              # a read-only profile must not stop the app
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
