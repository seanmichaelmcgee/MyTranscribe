"""Import an explicitly supplied local phone recording into the fictional trial corpus.

Keeps the original file and fixed references; converts only format/rate/channels.
Uses installed PyAV on CPU, with no model or network access. Native decoding runs
in one owned child with a timeout. Nothing is added to production recognition.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from asr_trial_common import local_result_path, sha256, write_json
from record_snippets import load_samples
from overnight_medasr import RunLock

SCRIPT = ROOT / "docs" / "samples" / "personal_v1.json"
SUFFIXES = {".wav", ".m4a", ".mp3", ".ogg", ".opus", ".aac", ".flac", ".webm", ".mp4", ".3gp"}
FORMATS = "wav,mov,mp3,ogg,aac,flac,matroska,webm"
MAX_BYTES = 100 * 1024 * 1024
MAX_SECONDS = 600


def deny_external_io(*args):
    raise OSError("External media references are not allowed")


def checked_source(source):
    source = Path(source).resolve(strict=True)
    if not source.is_file() or source.drive.startswith("\\\\") or source.suffix.lower() not in SUFFIXES:
        raise ValueError("Provide an original local audio file in a supported phone format")
    if not 0 < source.stat().st_size <= MAX_BYTES:
        raise ValueError("Phone file must be nonempty and at most 100 MiB")
    return source


def decode_to_wav(source, out, max_seconds=MAX_SECONDS):
    """Decode local bytes strictly and incrementally; reject rather than skip bad frames."""
    import av
    import numpy as np
    count, peak, squares, clipped = 0, 0, 0.0, 0
    with Path(source).open("rb") as raw, av.open(raw, mode="r", io_open=deny_external_io,
            options={"format_whitelist": FORMATS, "protocol_whitelist": "", "enable_drefs": "0"},
            timeout=(10, 10), metadata_errors="ignore") as container:
        if len(container.streams.audio) != 1 or container.streams.video:
            raise ValueError("Provide an audio-only recording with one audio track")
        context = container.streams.audio[0].codec_context
        source_info = dict(container=container.format.name, codec=context.name,
                           sample_rate=context.sample_rate, channels=context.layout.nb_channels)
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        with Path(out).open("xb") as handle, wave.open(handle, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)

            def write_frames(frames):
                nonlocal count, peak, squares, clipped
                for frame in frames:
                    samples = frame.to_ndarray().reshape(-1).astype("<i2", copy=False)
                    if count + len(samples) > int(max_seconds * 16000):
                        raise ValueError("Recording exceeds the import duration limit")
                    absolute = np.abs(samples.astype(np.int32))
                    peak = max(peak, int(absolute.max())) if len(samples) else peak
                    squares += float(np.square(samples.astype(np.float64)).sum())
                    clipped += int((absolute >= 32767).sum())
                    count += len(samples)
                    wav.writeframesraw(samples.tobytes())

            for frame in container.decode(audio=0):
                frame.pts = None
                write_frames(resampler.resample(frame))
            write_frames(resampler.resample(None))
        if count == 0:
            raise ValueError("No audio samples decoded")
    return dict(source_audio=source_info, seconds=count / 16000,
                decoder_pyav_version=av.__version__, decoder_library_versions=av.library_versions,
                output_rms=(squares / count) ** 0.5 / 32768,
                output_peak=peak / 32768, clipping_fraction=clipped / count,
                conversion="mono PCM int16 at 16000 Hz; no added gain, denoise or trimming")


def decode_in_worker(source, out):
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--decode-worker",
                                 str(source), str(out)], capture_output=True, text=True,
                                encoding="utf-8", timeout=90, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Phone audio decode timed out; no completed sample imported") from exc
    if result.returncode:
        raise ValueError("Phone audio could not be decoded; no completed sample imported")
    return json.loads(result.stdout)


def sample_reference(indices):
    rows = load_samples(SCRIPT)
    if not indices or len(indices) > len(rows) or any(i < 0 or i >= len(rows) for i in indices):
        raise ValueError("Specify one or more sample indices between 0 and 13")
    chosen = [rows[i] for i in indices]
    if len(chosen) == 1:
        return dict(chosen[0])
    return dict(scenario="pc_v1_combined_" + "_".join(str(i) for i in indices), category="combined",
                split="holdout" if any(row["split"] == "holdout" for row in chosen) else "calibration",
                spoken=" New paragraph. ".join(row["spoken"] for row in chosen),
                reference="\n\n".join(row["reference"] for row in chosen),
                terms=list(dict.fromkeys(term for row in chosen for term in row["terms"])), names=[])


def import_recording(source, out, indices, voice="normal", decoder=decode_in_worker):
    source = checked_source(source)
    if voice not in {"normal", "whisper"}:
        raise ValueError("Voice condition must be normal or whisper")
    packet_hash = sha256(SCRIPT)
    sample = sample_reference(indices)
    if sha256(SCRIPT) != packet_hash:
        raise ValueError("Reference changed while preparing import")
    input_hash = sha256(source)
    out = local_result_path(Path(out))
    out.mkdir(parents=True, exist_ok=True)
    with RunLock(out / ".phone_import.lock"):
        return import_locked(source, out, sample, indices, voice, decoder, packet_hash, input_hash)


def import_locked(source, out, sample, indices, voice, decoder, packet_hash, input_hash):
    manifest = out / "manifest.json"
    previous = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else []
    if any(row.get("sample_script_sha256") != packet_hash for row in previous):
        raise ValueError("Use a fresh output folder for a different sample packet")
    originals = local_result_path(out / "originals")
    originals.mkdir(exist_ok=True)
    identifier = uuid.uuid4().hex
    wav_path = out / ("phone_" + identifier + ".wav")
    partial = wav_path.with_suffix(".wav.partial")
    original = originals / (identifier + source.suffix.lower())
    try:
        diagnostics = decoder(source, partial)
        if sha256(source) != input_hash or sha256(SCRIPT) != packet_hash:
            raise ValueError("Input or reference changed during import")
        with source.open("rb") as incoming, original.open("xb") as saved:
            shutil.copyfileobj(incoming, saved)
        if sha256(original) != input_hash:
            raise ValueError("Original copy does not match the imported input")
        partial.rename(wav_path)
        row = dict(sample, audio=wav_path.name, profile="phone_file_" + voice,
                   seconds=diagnostics["seconds"], sample_script_sha256=packet_hash,
                   original_audio=original.relative_to(out).as_posix(), original_sha256=input_hash,
                   sample_indices=indices, reference_review_required=True,
                   importer_sha256=sha256(Path(__file__)))
        write_json(wav_path.with_suffix(".import.json"), dict(**diagnostics, original_sha256=input_hash,
                   normalized_sha256=sha256(wav_path), importer_sha256=sha256(Path(__file__)),
                   note="Phone file capture condition. Confirm intended reference before scoring."))
        write_json(manifest, previous + [row])
        return row
    finally:
        if partial.exists():
            partial.unlink()  # only this owned unpublished file; no recursive deletion


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--decode-worker":
        target = local_result_path(Path(sys.argv[3]))
        print(json.dumps(decode_to_wav(checked_source(sys.argv[2]), target)))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--samples", required=True, help="indices read, e.g. 6 or 0,3,6,7")
    parser.add_argument("--voice", choices=("normal", "whisper"), default="normal")
    parser.add_argument("--out", type=Path, help="ignored local results folder; default is separate per voice condition")
    args = parser.parse_args()
    out = args.out or ROOT / "results_1060" / ("phone_files_v1_" + args.voice)
    row = import_recording(args.input, out, [int(i) for i in args.samples.split(",")], args.voice)
    print(f"Imported {row['seconds']:.2f}s as {row['profile']}; reference confirmation required")


if __name__ == "__main__":
    main()
