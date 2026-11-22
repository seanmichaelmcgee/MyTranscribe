# Licences

## MyTranscribe Medical

The source code in this repository is open source under the **MIT License**
([LICENSE.txt](LICENSE.txt)). Word lists and data in the repository and where they come from:
[NOTICE.md](NOTICE.md).

## The Windows installer

The installer also contains the software the app runs on. Each part keeps its own licence. Before
installing, the installer shows a short summary ([installer/LICENSE-NOTICE.txt](installer/LICENSE-NOTICE.txt))
that the user accepts; a silent install (`/S`, for managed PCs) is taken as acceptance. The
installed folder holds every licence text: `THIRD-PARTY.txt` (each component, its licence and
where its text is), `NOTICE.md` and `licenses\`.

| Part | Licence | How it is shipped |
|---|---|---|
| Python 3.11 | Python Software Foundation License | `python\` |
| Qt 6.12 and Qt for Python (PySide6, shiboken6) | GNU LGPL v3 | separate libraries in `python\Lib\site-packages\PySide6`, which you may replace with your own builds. Source: [Qt](https://download.qt.io/official_releases/qt/6.12/), [Qt for Python](https://download.qt.io/official_releases/QtForPython/pyside6/) |
| pynput | GNU LGPL v3 | Python source, as installed |
| certifi, tqdm | Mozilla Public License 2.0 | Python source, as installed |
| faster-whisper, CTranslate2, ONNX Runtime, NumPy and the other packages | MIT, BSD, Apache 2.0, PSF | as installed |
| NVIDIA cuBLAS 12.9 (`cublas64_12.dll`, `cublasLt64_12.dll`) | NVIDIA CUDA Toolkit End User License Agreement (proprietary; its Attachment A lists these files as redistributable) | used only on a PC with an NVIDIA graphics card |
| Whisper speech models: small.en in the installer; large-v3 downloaded after asking | MIT (OpenAI; CTranslate2 conversions by Systran) | `models\`, or the user's Hugging Face cache |
| wordfreq word-frequency data | CC BY-SA 4.0 (wordfreq's code: Apache 2.0) | unmodified, as installed |

**Left out on purpose:** PyAV and the FFmpeg it bundles. Its Windows wheels link the GPL x264
and x265 video encoders, and the app never decodes audio files (it passes audio to Whisper as
arrays), so the installer carries a small placeholder module instead.

## Why PySide6

The app first used PyQt6, which is licensed under the GPL v3 (or commercially). An installer
built on it would have had to be distributed under the GPL as a whole, alongside NVIDIA's
proprietary cuBLAS. On 2026-11-22 it moved to PySide6, Qt's own Python binding under the LGPL
v3, so the app stays MIT and every bundled part is used under its own terms.

## Medical use

MyTranscribe is a dictation tool, not a medical device. It can make mistakes, including in drug
names, doses and numbers; the text must be read and corrected before it goes into a record. The
software comes without warranty (see the MIT License).

*This page summarises the licences; the licence texts themselves are what apply. It is not legal
advice.*
