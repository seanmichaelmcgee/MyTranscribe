"""
settings.py — the few user options for gui_med.py, saved as a small JSON file.

Location: %APPDATA%\\MyTranscribe\\settings.json on Windows
          (~/.config/mytranscribe/settings.json elsewhere).
Holds only key bindings, view and accuracy preferences: never transcript text.

Environment variables still override the file (handy for testing):
  MYTRANSCRIBE_KEY / MYTRANSCRIBE_KEY_MODE      e.g. f9 / hold|toggle, or none
  MYTRANSCRIBE_MOUSE / MYTRANSCRIBE_MOUSE_MODE  x2|x1|middle|none / hold|toggle
"""

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from triggers import KEY_CHOICES, MOUSE_CHOICES, TriggerConfig

logger = logging.getLogger("settings")


def default_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "MyTranscribe" / "settings.json"
    return Path.home() / ".config" / "mytranscribe" / "settings.json"


@dataclass
class Settings:
    key: str = "f9"                    # a KEY_CHOICES name, or "none"
    key_mode: str = "hold"             # "hold" | "toggle"
    mouse: str = "x2"                  # a MOUSE_CHOICES name, or "none"
    mouse_mode: str = "toggle"
    start_compact: bool = True
    accuracy: str = "best"             # "best" (large-v3 if the GPU allows) | "fast" (turbo)
    voice_commands: bool = True        # "new line", "new paragraph", "open/close quote"

    def triggers(self) -> TriggerConfig:
        return TriggerConfig(
            key=self.key if self.key in KEY_CHOICES else None, key_hold=self.key_mode == "hold",
            mouse=self.mouse if self.mouse in MOUSE_CHOICES else None, mouse_hold=self.mouse_mode == "hold",
        )

    def clean(self) -> "Settings":
        """Replace anything invalid (hand-edited file) with the default."""
        d = Settings()
        if self.key not in KEY_CHOICES and self.key != "none":
            self.key = d.key
        if self.mouse not in MOUSE_CHOICES and self.mouse != "none":
            self.mouse = d.mouse
        if self.key_mode not in ("hold", "toggle"):
            self.key_mode = d.key_mode
        if self.mouse_mode not in ("hold", "toggle"):
            self.mouse_mode = d.mouse_mode
        self.start_compact = bool(self.start_compact)
        self.voice_commands = bool(self.voice_commands)
        if self.accuracy not in ("best", "fast"):
            self.accuracy = d.accuracy
        return self


def load(path: Optional[Path] = None, env: Optional[dict] = None) -> Settings:
    path = path or default_path()
    env = os.environ if env is None else env
    s = Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(Settings)}
        s = Settings(**{k: v for k, v in data.items() if k in known})
    except FileNotFoundError:
        pass
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Ignoring unreadable settings file %s: %s", path, exc)
    for attr, var in (("key", "MYTRANSCRIBE_KEY"), ("key_mode", "MYTRANSCRIBE_KEY_MODE"),
                      ("mouse", "MYTRANSCRIBE_MOUSE"), ("mouse_mode", "MYTRANSCRIBE_MOUSE_MODE")):
        value = env.get(var, "").strip().lower()
        if value:
            setattr(s, attr, value)
    return s.clean()


def save(s: Settings, path: Optional[Path] = None) -> None:
    path = path or default_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(s.clean()), indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.error("Could not save settings to %s: %s", path, exc)
