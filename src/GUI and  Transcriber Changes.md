# GUI and Transcriber Changes

## Version 0.9 (Current)
- Added audio feedback chime when toggling transcription via hotkeys
- Created ChimePlayer utility for pleasant sound effects
- Improved resource management for audio components

## Version 0.8
- Added global hotkey support (Ctrl+Alt+Q) for toggling transcription from anywhere
- Added proper cleanup of keyboard listener on window close
- Implemented window raising when activated via global hotkey
- Added detailed logging for hotkey detection

## Version 0.7
- Added auto-clipboard copying of transcribed text
- Enhanced the transcription process with improved error handling
- Added technical vocabulary prompt for better handling of programming terms

## Version 0.6
- Added long recording mode (up to 3 minutes) for extended sessions
- Implemented auto-stop for long recordings to prevent memory issues
- Added audio activity indicator

## Version 0.5
- Added spacebar shortcut for toggling recording
- Improved transcription chunk processing with proper overlaps
- Implemented always-on-top window functionality

## Version 0.4
- Added GPU acceleration detection and utilization
- Implemented chunk-based transcription with overlap
- Added silence detection to skip empty audio segments

## Version 0.3
- Added hallucination filtering for common phrases
- Optimized audio processing for real-time use
- Improved error handling and logging

## Version 0.2
- Added GTK3-based user interface
- Implemented threading for non-blocking audio recording
- Added basic audio processing functionality

## Version 0.1
- Initial implementation with basic Whisper integration
- Simple audio recording functionality
- Command-line operation only