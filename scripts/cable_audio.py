"""
cable_audio.py: play 16 kHz mono audio into the VB-CABLE virtual audio cable.

Used by the live app trial (scripts/live_app_trial.py) to feed recordings into
the app's microphone input in real time. Needs VB-CABLE installed; the app (or
any other program) listens on "CABLE Output".
"""

import time

import numpy as np

SR = 16000
CABLE_PREFIX = "CABLE Input"


def pcm16(audio: np.ndarray) -> bytes:
    """float32 audio in [-1, 1] -> little-endian int16 bytes."""
    return (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()


def cable_output(pa):
    """The single MME 'CABLE Input' playback device (heard by other programs as 'CABLE Output')."""
    found = []
    for i in range(pa.get_device_count()):
        d = pa.get_device_info_by_index(i)
        if (d["maxOutputChannels"] > 0 and d["name"].startswith(CABLE_PREFIX)
                and pa.get_host_api_info_by_index(d["hostApi"])["name"] == "MME"):
            found.append(d)
    if len(found) != 1:
        raise RuntimeError(f"expected one '{CABLE_PREFIX}' playback device, found {len(found)}; is VB-CABLE installed?")
    return found[0]


def play(pcm: bytes) -> float:
    """Play 16 kHz mono PCM16 into the cable in real time; returns seconds taken."""
    import pyaudio
    pa = pyaudio.PyAudio()
    stream = None
    try:
        device = cable_output(pa)
        stream = pa.open(format=pyaudio.paInt16, channels=1, rate=SR, output=True,
                         output_device_index=int(device["index"]), frames_per_buffer=1024)
        start = time.monotonic()
        for offset in range(0, len(pcm), 2048):
            stream.write(pcm[offset:offset + 2048], exception_on_underflow=False)
        stream.stop_stream()
        return time.monotonic() - start
    finally:
        if stream is not None:
            stream.close()
        pa.terminate()
