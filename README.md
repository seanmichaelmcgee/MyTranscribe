# Real-Time Speech Transcription

A lightweight, GPU-accelerated real-time speech transcription application powered by OpenAI's Whisper model.

![Version](https://img.shields.io/badge/version-0.9-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## 🔍 Overview

This application provides real-time transcription of speech with a minimalist GTK interface. It's designed to be unobtrusive (stays on top with slight transparency) while efficiently transcribing speech in real-time using GPU acceleration when available.

This application was built primarily using iterative work on consumer-level LLMs and reasoner models, particularly OpenAI o3-mini-high and GPT 4o, as well as Claude 3.7 Thinking by Anthropic.

The application is optimized for English transcription but can easily be adjusted in the transcriber code. This application has been tested on two hardware configurations:

- Basic configuration: Ubuntu 24.04 with an NVIDIA 1660 Ti (6GB VRAM) and 9th gen Intel i7, using the "small" Whisper model
- Enhanced configuration: Modern system with an NVIDIA 4070 Ti, using the "medium"/"large" Whisper models for better quality transcription

The current version is configured for a 5-minute (300 second) automatic transcription window in normal mode, and long recording mode can record up to 3 minutes before processing automatically. These settings can be adjusted in the `transcriber_v12.py` file by modifying the `DEFAULT_CHUNK_DURATION` and long recording timeout values.

A green status bar indicates when audio is being detected. The audio chime feedback allows you to minimize the window to the background while still being aware of transcription state changes.

To run the application in typical fashion, open a terminal, activate your virtual environment, and run the GUI script:

## ✨ Features

- **Real-time transcription** with OpenAI's Whisper model (configurable from "small" to "large" size)
- **GPU acceleration** for improved performance on NVIDIA GPUs
- **Two recording modes**:
  - **Normal mode**: Processes audio in 5-minute chunks with 1-second overlap
  - **Long recording mode**: Captures extended speech (up to 3 minutes) before processing
- **Hardware adaptability**: Works with modest GPUs (1660 Ti) or more powerful ones (4070 Ti)
- **Optimized for technical vocabulary** with priming for programming/ML terminology
- **Keyboard shortcuts**:
  - Spacebar to toggle recording in normal mode (when window is focused)
  - Ctrl+Alt+Q to toggle recording from anywhere (global hotkey)
- **Audio feedback** with pleasant chime sound when toggling transcription
- **Auto-clipboard copying** of transcriptions
- **Minimal, always-on-top UI** with transparency
- **Background operation** with multiple launch options

## 🛠️ Installation

### Prerequisites

- Python 3.8+
- CUDA-compatible GPU (recommended but not required)
- GTK3 libraries
- FFmpeg

### Setup

1. **Create a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install --upgrade pip setuptools wheel
   pip install -r requirements.txt
   ```

3. **Install system dependencies** (if not already installed):
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 ffmpeg
   
   # macOS
   brew install pygobject3 gtk+3 ffmpeg
   ```

## 🚀 Usage

### Basic Usage

Run the application:
```bash
python src/gui-v0.8.py
```

### Running in Background

To run the application without keeping the terminal open, use:
```bash
nohup python src/gui-v0.8.py > /dev/null 2>&1 &
```

### Creating a Simple Alias

For convenience, you can add an alias to your `~/.bashrc` or `~/.zshrc` file:
```bash
# Add to ~/.bashrc
alias transcribe='cd /path/to/MyTranscribe && source venv/bin/activate && python src/gui-v0.8.py'

# Or for background running
alias transcribe-bg='cd /path/to/MyTranscribe && source venv/bin/activate && nohup python src/gui-v0.8.py > /dev/null 2>&1 &'
```
Then apply the changes:
```bash
source ~/.bashrc  # or source ~/.zshrc
```

### Creating a Desktop Shortcut

Create a desktop file at `~/.local/share/applications/mytranscribe.desktop`:
```
[Desktop Entry]
Name=MyTranscribe
Exec=bash -c "cd /path/to/MyTranscribe && source venv/bin/activate && python src/gui-v0.8.py"
Type=Application
Icon=/path/to/icon.png  # Optional
Comment=Real-time speech transcription
Terminal=false
Categories=Utility;AudioVideo;
```

### Controls

- **Start**: Begin transcribing in normal mode
- **Long Record**: Begin extended recording session 
- **Stop**: End recording and finalize transcription
- **Spacebar**: Toggle recording in normal mode (when window is focused)
- **Ctrl+Alt+Q**: Toggle recording in normal mode (works globally from any application)

With the audio chime feedback, you can minimize the window and still know when transcription starts/stops.

## 🏗️ Project Structure

```
├── src/gui-v0.8.py          # GTK user interface
├── src/transcriber_v12.py   # Whisper-based transcription engine
├── src/sound_utils.py       # Audio feedback utilities
└── requirements.txt         # Project dependencies
```

### Core Components

- **TranscriptionApp** (in gui-v0.8.py): Handles the GTK UI, button events, UI updating, and global hotkey support
- **RealTimeTranscriber** (in transcriber_v12.py): Manages audio recording, processing, and transcription
- **ChimePlayer** (in sound_utils.py): Provides audio feedback for user interactions

### Customization

#### Changing Whisper Model Size

To adjust the model size for better quality or faster transcription, edit `gui-v0.8.py` and modify the model loading line:

```python
# Line 74: Change "small" to "tiny", "base", "medium", or "large"
self.model = whisper.load_model("small", device=self.device)
```

Larger models provide better quality but require more VRAM and processing power:
- `tiny`: Fastest, lowest quality, ~1GB VRAM
- `base`: Good balance for weak GPUs, ~1GB VRAM
- `small`: Better quality, ~2GB VRAM
- `medium`: High quality, ~5GB VRAM
- `large`: Best quality, ~10GB VRAM

#### Modifying Recording Duration

To adjust the length of automatic transcription chunks in normal mode, edit `transcriber_v12.py`:

```python
# Line 16: Change recording duration (in seconds)
DEFAULT_CHUNK_DURATION = 300  # 5 minutes
```

To change the long recording mode auto-stop duration:

```python
# Line 138: Adjust the timeout duration (in seconds)
if time.time() - self.long_start_time >= 180:  # 3 minutes
    self.running = False
```

## 🔮 Future Development

### Docker Containerization

The next development phase will focus on containerizing this application:

- Create a Dockerfile optimized for GPU passthrough
- Ensure CUDA compatibility in the container
- Minimize image size by removing unnecessary dependencies
- Add volume mounting for persistent storage of transcriptions
- Implement environment variables for configuration

### Other Planned Improvements

- Fine-tuning Whisper for specific domains or vocabularies
- Adding language support beyond English
- Implementing post-processing to improve grammar and remove filler words
- UI improvements including theme support

## Distribution

Library dependencies for GPU acceleration make packaging complex. Containerized distribution is a possibility, but requires a higher level of user knowledge. ONNX runtime could potentially offer an alternative path for optimization.

In the meantime, it's recommended to run the application from the terminal within a virtual environment after installing the necessary dependencies.


## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgements

- [OpenAI Whisper](https://github.com/openai/whisper) for the speech recognition model
- [PyTorch](https://pytorch.org/) for GPU acceleration
- [GTK](https://www.gtk.org/) for the user interface