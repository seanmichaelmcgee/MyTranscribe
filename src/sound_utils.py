import os
import math
import numpy as np
import pyaudio
import wave
import tempfile
import threading
import logging

# Constants for audio generation
SAMPLE_RATE = 44100  # Hz
DURATION = 0.2      # seconds
VOLUME = 0.3        # amplitude (0.0-1.0)

def generate_chime_file():
    """Generate a pleasant sounding chime and save it to a temp file."""
    temp_dir = tempfile.gettempdir()
    chime_path = os.path.join(temp_dir, "mytranscribe_chime.wav")
    
    # Don't regenerate if file already exists
    if os.path.exists(chime_path):
        return chime_path

    # Generate a pleasant chime sound (a simple chord)
    t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)
    
    # Generate a chord with multiple harmonics for a pleasant bell-like sound
    notes = [523.25, 659.25, 783.99]  # C5, E5, G5 frequencies
    signal = np.zeros_like(t)
    
    for note in notes:
        # Add the note with an exponential decay
        decay = np.exp(-5 * t)
        tone = np.sin(2 * np.pi * note * t) * decay
        signal += tone
    
    # Normalize to the desired volume
    signal *= VOLUME / np.max(np.abs(signal))
    
    # Convert to 16-bit PCM
    signal = (signal * 32767).astype(np.int16)
    
    # Save as WAV file
    with wave.open(chime_path, 'wb') as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(signal.tobytes())
    
    logging.debug(f"Generated chime file at {chime_path}")
    return chime_path

class ChimePlayer:
    """A simple player for chime sounds."""
    def __init__(self):
        self.chime_path = generate_chime_file()
        self.p = pyaudio.PyAudio()
        self.is_playing = False
        self._lock = threading.Lock()
    
    def play(self):
        """Play the chime sound in a separate thread."""
        if self.is_playing:
            return
            
        # Start a new thread to play the sound
        threading.Thread(target=self._play_sound_thread, daemon=True).start()
    
    def _play_sound_thread(self):
        """Thread function to play the sound."""
        with self._lock:
            if self.is_playing:
                return
            self.is_playing = True
        
        try:
            with wave.open(self.chime_path, 'rb') as wf:
                stream = self.p.open(
                    format=self.p.get_format_from_width(wf.getsampwidth()),
                    channels=wf.getnchannels(),
                    rate=wf.getframerate(),
                    output=True
                )
                
                data = wf.readframes(1024)
                while data:
                    stream.write(data)
                    data = wf.readframes(1024)
                
                stream.stop_stream()
                stream.close()
        except Exception as e:
            logging.error(f"Error playing chime sound: {e}")
        finally:
            with self._lock:
                self.is_playing = False
    
    def cleanup(self):
        """Clean up resources."""
        if self.p:
            self.p.terminate()
            self.p = None