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

def generate_start_chime_file():
    """Generate a pleasant ascending chime for start of transcription."""
    temp_dir = tempfile.gettempdir()
    chime_path = os.path.join(temp_dir, "mytranscribe_start_chime.wav")
    
    # Force regeneration this one time
    if os.path.exists(chime_path):
        try:
            os.remove(chime_path)
        except:
            pass

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
    
    logging.debug(f"Generated start chime file at {chime_path}")
    return chime_path

def generate_end_chime_file():
    """Generate a descending chime for end of transcription."""
    temp_dir = tempfile.gettempdir()
    chime_path = os.path.join(temp_dir, "mytranscribe_end_chime.wav")
    
    # Force regeneration this one time
    if os.path.exists(chime_path):
        try:
            os.remove(chime_path)
        except:
            pass

    # Generate a pleasant descending chime sound
    t = np.linspace(0, DURATION, int(SAMPLE_RATE * DURATION), False)
    
    # Generate a descending chord with lower notes
    notes = [659.25, 523.25, 392.00]  # E5, C5, G4 frequencies (descending)
    signal = np.zeros_like(t)
    
    for i, note in enumerate(notes):
        # Add a slight delay to each successive note for a descending effect
        delay = i * 0.04  # Each note starts a bit later
        # Create time array with delay
        t_note = np.maximum(t - delay, 0)
        # Add the note with an exponential decay
        decay = np.exp(-5 * t_note)
        tone = np.sin(2 * np.pi * note * t_note) * decay
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
    
    logging.debug(f"Generated end chime file at {chime_path}")
    return chime_path

class ChimePlayer:
    """A player for start and end chime sounds."""
    def __init__(self):
        self.start_chime_path = generate_start_chime_file()
        self.end_chime_path = generate_end_chime_file()
        self.p = pyaudio.PyAudio()
        self.is_playing = False
        self._lock = threading.Lock()
    
    def play_start(self):
        """Play the start chime sound in a separate thread."""
        if self.is_playing:
            return
            
        # Start a new thread to play the sound
        threading.Thread(target=self._play_sound_thread, args=(self.start_chime_path,), daemon=True).start()
    
    def play_end(self):
        """Play the end chime sound in a separate thread."""
        if self.is_playing:
            return
            
        # Start a new thread to play the sound
        threading.Thread(target=self._play_sound_thread, args=(self.end_chime_path,), daemon=True).start()
    
    def play(self):
        """Legacy method to play the start chime for backward compatibility."""
        self.play_start()
    
    def _play_sound_thread(self, sound_path):
        """Thread function to play the sound."""
        with self._lock:
            if self.is_playing:
                return
            self.is_playing = True
        
        try:
            with wave.open(sound_path, 'rb') as wf:
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