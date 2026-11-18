"""
mic_check.py — the microphone check in the setup wizard and Options.

Records a few seconds of quiet, then one fictional sentence read aloud, from the
chosen microphone *before* the app's gain. From those it measures room noise,
speech level and peaks, suggests a gain (Options → Microphone gain) and lists
plain-language warnings. Nothing is saved or transcribed; the audio is dropped
when the check ends.

The gain rule is deliberately conservative: a level that is already fine is left
as the microphone sends it (gain 50). It changes the gain only when speech is
too quiet to clear the app's speech-level check comfortably, or so loud that it
reaches the top of the range. Gain has not been shown to change word errors at a
good level; it matters at the extremes, where quiet speech can be taken for
silence and clipped speech is distorted.
"""

import math
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from chunked_transcriber import (FRAMES_PER_BUFFER, GAIN_DB_PER_STEP, LEVEL_THRESHOLD_RMS, SAMPLE_RATE,
                                 InputLevel, gain_from_slider, input_level, int16_bytes_to_float32)

QUIET_S = 3.0
SPEAK_S = 7.0
FRAME_S = 0.05
TARGET_SPEECH_DB = -24.0        # loud frames of speech (90th percentile of 50 ms frames)
GOOD_SPEECH_DB = (-34.0, -12.0)  # left as it is inside this band
PEAK_CEILING_DB = -3.0          # after the suggested gain
CLIP_PEAK = 0.98
THRESHOLD_DB = 20 * math.log10(LEVEL_THRESHOLD_RMS / 32768)   # the app's speech-level check, about -52 dBFS
NOISE_MARGIN_DB = 6.0           # raised gain keeps the room's noise this far under that check
QUIET_WARN_DB = -40.0           # speech still under this after the gain: say so
HEARD_MIN_DB = 10.0             # speech must stand this far above the quiet part to count as heard
CLEAN_SNR_DB = 20.0

# Fictional; read during the check.
CHECK_SENTENCE = ("Mrs. Jones is a 64-year-old woman seen today for follow-up of hypertension "
                  "and type 2 diabetes. Her blood pressure is 132 over 78.")


def meter_display(level: InputLevel) -> tuple:
    """Logarithmic level bar (0..100) and its colour kind: 'low' (amber), 'signal' (green), 'clipping' (red)."""
    value = round(max(0.0, min(100.0, (level.dbfs + 60) * 100 / 60)))
    kind = ("clipping" if level.peak >= 0.999 else
            "low" if level.rms * 32768 <= LEVEL_THRESHOLD_RMS else "signal")
    return value, kind


def _db(x: float) -> float:
    return 20 * math.log10(x) if x > 0 else -120.0


def frame_rms(samples: np.ndarray, frame_s: float = FRAME_S, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    win = max(1, int(frame_s * sample_rate))
    usable = (samples.size // win) * win
    if usable == 0:
        return np.zeros(0, dtype=np.float32)
    frames = samples[:usable].astype(np.float32).reshape(-1, win)
    return np.sqrt(np.mean(np.square(frames), axis=1))


def slider_for_db(gain_db: float) -> int:
    return int(max(0, min(100, 50 + round(gain_db / GAIN_DB_PER_STEP))))


@dataclass
class MicCheckResult:
    heard: bool
    noise_db: float                 # median 50 ms level while quiet (dBFS, before gain)
    speech_db: float                # 90th percentile 50 ms level while reading
    peak: float                     # largest sample while reading (0..1)
    gain: int                       # suggested Options → Microphone gain (0..100)
    warnings: List[str] = field(default_factory=list)

    @property
    def gain_db(self) -> float:
        return (self.gain - 50) * GAIN_DB_PER_STEP

    @property
    def separation_db(self) -> float:
        return self.speech_db - self.noise_db

    def summary(self) -> str:
        """One plain sentence for the person, with the numbers for anyone who wants them."""
        if not self.heard:
            return "Hardly any sound came through while you read."
        level = ("good" if GOOD_SPEECH_DB[0] <= self.speech_db <= GOOD_SPEECH_DB[1] and self.peak < CLIP_PEAK
                 else "too loud" if self.peak >= CLIP_PEAK or self.speech_db > GOOD_SPEECH_DB[1] else "quiet")
        room = "quiet" if self.noise_db + self.gain_db <= THRESHOLD_DB else "noisy"
        gain = ("left as the microphone sends it" if self.gain == 50 else
                f"set to {self.gain} ({'+' if self.gain_db > 0 else '−'}{abs(self.gain_db):.0f} dB)")
        return (f"Your voice: {level}. Background: {room}. Gain {gain}. "
                f"(Speech {self.speech_db:.0f} dBFS, background {self.noise_db:.0f} dBFS, "
                f"{self.separation_db:.0f} dB apart.)")


def analyse(quiet: np.ndarray, speech: np.ndarray, bluetooth: bool = False) -> MicCheckResult:
    """quiet / speech: float32 samples in -1..1 as the microphone sent them (before the app's gain)."""
    q, s = frame_rms(quiet), frame_rms(speech)
    noise_db = _db(float(np.median(q))) if q.size else -120.0
    speech_db = _db(float(np.percentile(s, 90))) if s.size else -120.0
    peak = float(np.max(np.abs(speech))) if speech.size else 0.0
    heard = speech_db > -60 and speech_db - noise_db >= HEARD_MIN_DB
    warnings: List[str] = []
    if not heard:
        warnings.append("Hardly any sound came through. Check that this is the microphone you speak into, that it "
                        "is not muted, and that Windows lets apps use it (Settings → Privacy & security → "
                        "Microphone). Then check again.")
        return MicCheckResult(False, noise_db, speech_db, peak, 50, warnings)

    if GOOD_SPEECH_DB[0] <= speech_db <= GOOD_SPEECH_DB[1] and peak < CLIP_PEAK:
        gain_db = 0.0
    else:
        gain_db = TARGET_SPEECH_DB - speech_db
        if peak > 0:
            gain_db = min(gain_db, PEAK_CEILING_DB - _db(peak))
        if gain_db > 0:                      # never lift the room's noise up to where it counts as sound
            gain_db = min(gain_db, max(0.0, THRESHOLD_DB - NOISE_MARGIN_DB - noise_db))
        gain_db = max(-20.0, min(20.0, gain_db))
    gain = slider_for_db(gain_db)
    gain_db = (gain - 50) * GAIN_DB_PER_STEP

    if peak >= CLIP_PEAK:
        warnings.append("Your voice reached the top of the microphone's range, which distorts it. The gain has been "
                        "lowered; if the level bar still turns red, move the microphone a little further from "
                        "your mouth or lower its level in Windows.")
    if speech_db + gain_db < QUIET_WARN_DB:
        warnings.append("Your voice is still quiet after raising the gain. Raise the microphone's level in Windows "
                        "(Settings → System → Sound → Input) or move the microphone closer, then check again.")
    if noise_db + gain_db > THRESHOLD_DB:
        warnings.append("The background is loud enough to count as sound when you pause, which can add stray "
                        "words. A microphone closer to your mouth or a quieter room helps.")
    elif speech_db - noise_db < CLEAN_SNR_DB:
        warnings.append(f"Your voice is only {speech_db - noise_db:.0f} dB above the background. A headset "
                        "microphone close to your mouth gives cleaner text.")
    if bluetooth:
        warnings.append("This looks like a Bluetooth headset. It works, but Bluetooth sends lower-quality sound "
                        "from the microphone and takes a moment to wake up (Keep microphone ready covers that). "
                        "A wired or USB headset usually sounds clearer.")
    return MicCheckResult(True, noise_db, speech_db, peak, gain, warnings)


class MicMonitor:
    """
    Reads one microphone on its own thread for the level bar and the check.
    level (after `gain`) is read by the GUI; record() collects raw samples.
    open_stream(device) -> (stream, owner) is injectable for tests.
    """

    def __init__(self, device: str = "", open_stream: Optional[Callable] = None, gain: int = 50) -> None:
        if open_stream is None:
            from chunked_transcriber import _default_stream_factory
            open_stream = _default_stream_factory
        self._open = open_stream
        self.device = device
        self.gain = gain
        self.level = InputLevel()
        self.error: Optional[str] = None
        self._lock = threading.Lock()
        self._collect: Optional[list] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.error = None
        self._thread = threading.Thread(target=self._loop, name="mic-check", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        with self._lock:
            self._collect = None
        self.level = InputLevel()

    @property
    def running(self) -> bool:
        return self._running

    def begin_recording(self) -> None:
        with self._lock:
            self._collect = []

    def end_recording(self) -> np.ndarray:
        with self._lock:
            frames, self._collect = self._collect or [], None
        return int16_bytes_to_float32(b"".join(frames)) if frames else np.zeros(0, dtype=np.float32)

    def _loop(self) -> None:
        from chunked_transcriber import apply_gain
        stream = owner = None
        try:
            stream, owner = self._open(self.device)
        except Exception as exc:
            self.error = f"Could not open the microphone: {exc}"
            self._running = False
            return
        try:
            while self._running:
                try:
                    data = stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False)
                except Exception as exc:
                    self.error = f"The microphone stopped sending sound: {exc}"
                    break
                if not data:
                    break
                with self._lock:
                    if self._collect is not None:
                        self._collect.append(data)
                self.level = input_level(apply_gain(data, gain_from_slider(self.gain)))
        finally:
            self._running = False
            for obj, op in ((stream, "stop_stream"), (stream, "close"), (owner, "terminate")):
                if obj is not None:
                    try:
                        getattr(obj, op)()
                    except Exception:
                        pass
