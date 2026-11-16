"""
settings.py — the few user options for gui_med.py, saved as a small JSON file.

Location: %APPDATA%\\MyTranscribe\\settings.json on Windows
          (~/.config/mytranscribe/settings.json elsewhere).
Holds only key bindings, view and accuracy preferences: never transcript text.

Environment variables still override the file (handy for testing):
  MYTRANSCRIBE_KEY / MYTRANSCRIBE_KEY_MODE      e.g. f9 / hold|toggle, or none
  MYTRANSCRIBE_MOUSE / MYTRANSCRIBE_MOUSE_MODE  x2|x1|middle|none / hold|toggle
  MYTRANSCRIBE_LANGUAGE                         en|es|fr|sw: the dictation language
  MYTRANSCRIBE_ENGINE                           whisper|medasr|parakeet|canary: the recogniser
  MYTRANSCRIBE_PAUSE_AWARE                      1|0: pause-aware dictation on/off
  MYTRANSCRIBE_SPOKEN_PUNCTUATION               1|0: convert dictated punctuation marks on/off
  MYTRANSCRIBE_EXTRA_FIXES                      1|0: same-sound term correction and readings format on/off
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


ENGINE_CHOICES = ("whisper", "medasr", "parakeet", "canary")
LANGUAGE_CHOICES = ("en", "es", "fr", "sw")


@dataclass
class Settings:
    key: str = "f9"                    # a KEY_CHOICES name, or "none"
    key_mode: str = "hold"             # "hold" | "toggle"
    mouse: str = "x2"                  # a MOUSE_CHOICES name, or "none"
    mouse_mode: str = "toggle"
    start_compact: bool = True
    accuracy: str = "best"             # "best" (large-v3 if the GPU allows) | "fast" (turbo)
    language: str = "en"               # dictation language: en | es | fr | sw (lang_packs.py)
    engine: str = "whisper"            # recogniser: whisper | medasr | parakeet | canary (engines.py)
    voice_commands: bool = True        # "new line", "new paragraph", "open/close quote"
    keep_mic_ready: bool = True        # mic open between dictations + 0.5 s pre-roll (like Dragon)
    live_insert: bool = False          # paste each ~30 s piece at the cursor while dictating

    chime_volume: int = 100           # percent of the original chime level; zero mutes
    autopaste: bool = False
    pause_aware: bool = False          # pause-aware dictation (see pause_flow.py); off = classic pipeline
    extra_fixes: bool = False          # same-sound drug-name correction + readings format (138/78, g/L)
    spoken_punctuation: bool = False   # "period", "comma", "colon" ... -> the marks (voice_commands.py)

    def triggers(self) -> TriggerConfig:
        return TriggerConfig(
            key=self.key if self.key in KEY_CHOICES else None, key_hold=self.key_mode == "hold",
            mouse=self.mouse if self.mouse in MOUSE_CHOICES else None, mouse_hold=self.mouse_mode == "hold",
        )

    def clean(self) -> "Settings":
        """Replace anything invalid (hand-edited file) with the default."""
        d = Settings()
        try:
            self.chime_volume = max(0, min(100, int(self.chime_volume)))
        except (ValueError, TypeError, OverflowError):
            self.chime_volume = d.chime_volume
        self.autopaste = bool(self.autopaste)
        self.pause_aware = bool(self.pause_aware)
        self.spoken_punctuation = bool(self.spoken_punctuation)
        self.extra_fixes = bool(self.extra_fixes)
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
        self.keep_mic_ready = bool(self.keep_mic_ready)
        self.live_insert = bool(self.live_insert)
        if self.accuracy not in ("best", "fast"):
            self.accuracy = d.accuracy
        if self.engine not in ENGINE_CHOICES:
            self.engine = d.engine
        if self.language not in LANGUAGE_CHOICES:
            self.language = d.language
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
    forced_language = env.get("MYTRANSCRIBE_LANGUAGE", "").strip().lower()
    if forced_language:
        s.language = forced_language
    forced_engine = env.get("MYTRANSCRIBE_ENGINE", "").strip().lower()
    if forced_engine:
        s.engine = forced_engine
    for attr, var in (("pause_aware", "MYTRANSCRIBE_PAUSE_AWARE"),
                      ("spoken_punctuation", "MYTRANSCRIBE_SPOKEN_PUNCTUATION"),
                      ("extra_fixes", "MYTRANSCRIBE_EXTRA_FIXES")):
        forced = env.get(var, "").strip().lower()
        if forced:
            setattr(s, attr, forced in ("1", "true", "yes", "on"))
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
