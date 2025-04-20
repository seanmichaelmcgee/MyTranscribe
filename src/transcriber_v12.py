import threading
import pyaudio
import wave
import time
import tempfile
import os
import logging
import whisper
import torch
import numpy as np

# Audio configuration
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
DEFAULT_CHUNK_DURATION = 300  # seconds for normal mode processing
OVERLAP_DURATION = 1 # 1 second overlap

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Technical prompt for improved transcription accuracy with mitigation for hallucinations
TECHNICAL_PROMPT = (
    "This audio includes detailed technical content about Python development, "
    "machine learning, and software engineering workflows. Topics may involve "
    "Git, GitHub, version control (branches, commits, pull requests), coding in "
    "VS Code or Ubuntu, and libraries like PyTorch or TensorFlow. Please "
    "transcribe all technical terms accurately (e.g., 'git push,' 'virtual "
    "environment,' 'docker container,' 'backpropagation,' 'gradient descent,' "
    "'PyTorch Lightning,' etc.) while preserving overall clarity for standard "
    "English text. Do not add introductory phrases like 'thank you', 'thank you "
    "for watching', 'welcome', or other greeting/closing phrases unless they are "
    "clearly spoken in the audio. Only transcribe what is actually said."
)

class RealTimeTranscriber:
    def __init__(self, model):
        self.model = model
        # Move model to GPU if available
        if torch.cuda.is_available():
            self.model.to("cuda")
        if next(self.model.parameters()).is_cuda:
            logging.info("GPU acceleration is enabled.")
        else:
            logging.info("GPU acceleration is NOT enabled.")
        
        self.transcriptions = []
        self.running = False
        self.partial_frames = []
        self.overlap_frames = []
        self.audio_interface = pyaudio.PyAudio()
        self.num_overlap_buffers = int((OVERLAP_DURATION * 16000) / CHUNK)
        self.chunk_duration = DEFAULT_CHUNK_DURATION  # for normal mode

        # For long record mode
        self.long_mode = False
        self.long_frames = []
        
        # For audio detection - simplified to a boolean flag
        self.audio_detected = False
        # Counter to maintain the indicator visible for a short period
        self.audio_detection_counter = 0

    def start_recording(self, mode="normal"):
        """
        mode: "normal" for normal incremental transcription,
              "long" for accumulating audio until session end (max 180 seconds auto-stop)
        """
        self.long_mode = (mode == "long")
        self.chunk_duration = DEFAULT_CHUNK_DURATION  # used in normal mode
        self.running = True
        self.overlap_frames = []
        self.partial_frames = []
        
        if self.long_mode:
            self.long_frames = []
            self.long_start_time = time.time()
        # Open audio stream
        self.stream = self.audio_interface.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=16000,
            input=True,
            frames_per_buffer=CHUNK
        )
        self.record_thread = threading.Thread(target=self.record_loop, daemon=True)
        self.record_thread.start()

    def stop_recording(self):
        self.running = False
        if self.record_thread.is_alive():
            self.record_thread.join()
        self.stream.stop_stream()
        self.stream.close()
        # Reset audio detection when stopped
        self.audio_detected = False
        self.audio_detection_counter = 0

    def calculate_audio_level(self, audio_data):
        """Detect if audio data contains speech above threshold."""
        # Convert bytes to int16 array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Check if audio_array is empty (to avoid division by zero)
        if len(audio_array) == 0:
            return
            
        # Calculate RMS (Root Mean Square)
        rms = np.sqrt(np.mean(np.square(audio_array.astype(np.float32))))
        
        # Threshold for detecting active speech (may need adjustment)
        threshold = 300
        
        # Set the detection flag if audio is above threshold
        if rms > threshold:
            self.audio_detected = True
            # Set counter to keep indicator visible for a short time (about 300ms)
            self.audio_detection_counter = 10
        elif self.audio_detection_counter > 0:
            # Decrement counter if no audio detected but counter is still active
            self.audio_detection_counter -= 1
        else:
            # Turn off indicator when counter reaches zero
            self.audio_detected = False

    def record_loop(self):
        if self.long_mode:
            # In long mode, simply accumulate all audio frames.
            while self.running:
                try:
                    data = self.stream.read(CHUNK, exception_on_overflow=False)
                    # Calculate audio level
                    self.calculate_audio_level(data)
                except Exception as e:
                    logging.error("Error reading audio stream", exc_info=True)
                    continue
                self.long_frames.append(data)
                # Auto-stop after 180 seconds if not interrupted
                if time.time() - self.long_start_time >= 180:
                    self.running = False
            # Once stopped, process the entire accumulated audio as one chunk.
            if self.long_frames:
                self.process_audio_chunk(self.long_frames)
        else:
            # Normal mode: process audio in DEFAULT_CHUNK_DURATION-second chunks.
            while self.running:
                frames = []
                chunk_start = time.time()
                while time.time() - chunk_start < self.chunk_duration:
                    if not self.running:
                        break
                    try:
                        data = self.stream.read(CHUNK, exception_on_overflow=False)
                        # Calculate audio level
                        self.calculate_audio_level(data)
                    except Exception as e:
                        logging.error("Error reading audio stream", exc_info=True)
                        continue
                    frames.append(data)
                if not frames:
                    continue
                all_frames = self.overlap_frames + frames
                if all_frames:
                    self.process_audio_chunk(all_frames)
                if len(all_frames) >= self.num_overlap_buffers:
                    self.overlap_frames = all_frames[-self.num_overlap_buffers:]
                else:
                    self.overlap_frames = all_frames

    def process_audio_chunk(self, frames):
        if not frames:
            return
        wav_filename = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_wav:
                wav_filename = temp_wav.name
            with wave.open(wav_filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.audio_interface.get_sample_size(FORMAT))
                wf.setframerate(16000)
                wf.writeframes(b''.join(frames))
            
            # Check if the audio contains actual speech
            if self.is_silent(frames):
                logging.info("Chunk contains mostly silence, skipping transcription")
                return
                
            use_fp16 = next(self.model.parameters()).is_cuda
            result = self.model.transcribe(
                wav_filename,
                fp16=use_fp16,
                language="en",
                task="transcribe",
                initial_prompt=TECHNICAL_PROMPT,
                # Added temperature parameter to reduce hallucinations
                temperature=0.0,
                # Added condition_on_previous_text=False to prevent the model from
                # generating content based on what it "expects" to hear
                condition_on_previous_text=False
            )
            
            new_text = result.get("text", "").strip()
            
            # Additional filter to catch remaining hallucinated greetings/closings
            filtered_text = self.filter_hallucinated_phrases(new_text)
            
            # Only add non-empty transcriptions
            if filtered_text:
                self.transcriptions.append(filtered_text)
        except RuntimeError as e:
            if "Expected key.size(1) == value.size(1)" in str(e):
                msg = "[Transcription Error: shape mismatch, skipping this chunk]"
                logging.error(msg, exc_info=True)
                self.transcriptions.append(msg)
            else:
                logging.error("Transcription error", exc_info=True)
                self.transcriptions.append(f"[Transcription Error: {e}]")
        except Exception as e:
            logging.error("Transcription error", exc_info=True)
            self.transcriptions.append(f"[Transcription Error: {e}]")
        finally:
            if wav_filename and os.path.exists(wav_filename):
                os.remove(wav_filename)
        self.partial_frames = []

    def force_process_partial_frames(self):
        try:
            if self.running and self.stream.is_active():
                data = self.stream.read(self.stream.get_read_available(), exception_on_overflow=False)
                if self.long_mode:
                    self.long_frames.append(data)
                else:
                    self.partial_frames.append(data)
        except Exception:
            pass
        if not self.long_mode:
            final_frames = self.overlap_frames + self.partial_frames
            if final_frames:
                self.process_audio_chunk(final_frames)
                
    def is_silent(self, frames):
        """Detect if audio frames contain mostly silence."""
        if not frames:
            return True
            
        # Join frames into a single buffer
        buffer = b''.join(frames)
        
        # Convert to numpy array for analysis
        audio_array = np.frombuffer(buffer, dtype=np.int16)
        
        if len(audio_array) == 0:
            return True
            
        # Calculate RMS energy
        rms = np.sqrt(np.mean(np.square(audio_array.astype(np.float32))))
        
        # Define a threshold for silence (adjust based on your microphone and environment)
        # The threshold of 500 is a reasonable starting point but may need adjustment
        silence_threshold = 300
        
        # If the RMS is below the threshold, consider it silence
        return rms < silence_threshold
        
    def filter_hallucinated_phrases(self, text):
        """Remove common hallucinated phrases from the transcription."""
        if not text:
            return text
            
        # Common phrases that Whisper often hallucinates at the beginning
        common_hallucinations = [
            "thank you for watching",
            "thanks for watching",
            "thank you",
            "thanks",
            "welcome to",
            "welcome back",
            "hello everyone",
            "hi everyone"
        ]
        
        # Check for hallucinated phrases at the beginning of the text
        lower_text = text.lower()
        for phrase in common_hallucinations:
            if lower_text.startswith(phrase):
                # Remove the phrase and any following whitespace
                text = text[len(phrase):].lstrip()
                # Start checking again with the shortened text
                lower_text = text.lower()
        
        return text