# System Dependencies

> **Note:** The following dependencies must be installed system-wide (using your package manager, e.g., apt-get on Ubuntu) because they provide the libraries and header files required to compile native Python extensions. These are not installed in your Python virtual environment.

## Python Packages
The application now uses the `pynput` package for global hotkey functionality. This is included in the `requirements.txt` file and will be installed when you run `pip install -r requirements.txt`.

- **libcairo2-dev**: Development files for the Cairo graphics library, required by the `pycairo` package.
- **pkg-config**: A helper tool used to retrieve information about installed libraries, ensuring the correct compile and link flags are used.
- **python3-dev**: Contains Python header files and a static library necessary for compiling Python C extensions.
- **libgirepository1.0-dev**: Provides the development files for GObject Introspection, which is required by the `pygobject` package.
- **portaudio19-dev**: Supplies the development files for PortAudio, necessary for building the `PyAudio` package.

## ffmpeg Installation Requirement

This project requires **ffmpeg** to be installed and available in your system's PATH. If you encounter the error:

    FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'

it means that **ffmpeg** is missing. To resolve this, please install **ffmpeg**.

For Debian/Ubuntu systems, you can install it using:
    
    sudo apt-get update
    sudo apt-get install ffmpeg

For other platforms, refer to your distribution's installation guidelines for **ffmpeg**.
## ALSA and JACK Dependencies for Microphone Input

If you're experiencing issues with microphone input (e.g., errors like "ALSA lib pcm.c:... Unknown PCM" or "jack server is not running"), it may indicate that your system's audio configuration is not set up correctly for this project.

### ALSA (Advanced Linux Sound Architecture)
- Ensure ALSA is installed and properly configured.
- On Debian/Ubuntu systems, install ALSA utilities with:
  
  sudo apt-get install alsa-utils
  
- Test available recording devices using:
  
  arecord -l

### JACK (Jack Audio Connection Kit)
- JACK may be required for low-latency audio processing in some configurations.
- **Note:** If your microphone is properly set up and working via ALSA (as shown by `arecord -l`), JACK may not be necessary.
- If you do need JACK, install it on Debian/Ubuntu with:
  
  sudo apt-get install jackd2
  
- To start the JACK server, run:
  
  jackd -d alsa
  
- Optionally, use a graphical frontend like qjackctl:
  
  sudo apt-get install qjackctl

Adjust your system's audio settings as necessary and refer to ALSA and JACK documentation for additional troubleshooting if your microphone still isn't detected.