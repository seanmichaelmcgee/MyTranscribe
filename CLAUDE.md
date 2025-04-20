# MyTranscribe Development Guide

## Usage Commands
- Run application: `python gui-v0.8.py`
- Setup virtual environment: `python3 -m venv venv && source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Install system dependencies: `sudo apt-get install python3-gi python3-gi-cairo gir1.2-gtk-3.0 ffmpeg portaudio19-dev libcairo2-dev pkg-config python3-dev libgirepository1.0-dev`

## Code Style Guidelines
- **Formatting**: Use 4-space indentation
- **Naming**: Use snake_case for functions/variables, CamelCase for classes
- **Imports**: Group standard library, third-party, and local imports with blank lines between groups
- **Error Handling**: Use try/except blocks with specific exceptions and logging
- **Documentation**: Document functions with docstrings explaining purpose and parameters
- **Type Hints**: Not currently used but encouraged for new code
- **Logging**: Use the logging module with appropriate levels (info, error)
- **UI Components**: Follow GTK3 widget patterns with consistent styling
- **Audio Processing**: Document chunk size, format, and rate when modified