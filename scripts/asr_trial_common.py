"""Local trial provenance and PCM input. No model, GUI, microphone or network imports."""
import hashlib
import json
import os
import subprocess
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "google/medasr"
MODEL_REVISION = "ae1e4845b4b07479735d93e1e591e566435b7104"
MODEL_FILES = (
    "config.json", "model.safetensors", "preprocessor_config.json",
    "processor_config.json", "tokenizer.json", "tokenizer_config.json",
    "added_tokens.json", "spiece.model",
)
SR = 16000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def write_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def local_result_path(path: Path) -> Path:
    path = path.resolve()
    relative = path.relative_to(ROOT)
    if not relative.parts or not relative.parts[0].startswith("results_"):
        raise ValueError("Trial output must be inside a gitignored results_* directory")
    git = os.environ.get("GIT", "git")
    check = subprocess.run([git, "check-ignore", "--quiet", str(path)], cwd=ROOT)
    if check.returncode != 0:
        raise ValueError("Trial output directory must be gitignored")
    return path


def load_corpus(manifests: list[Path], only: str | None = None) -> tuple[list[dict], str]:
    entries, seen = [], set()
    categories = set(only.split(",")) if only else None
    for manifest in manifests:
        manifest = manifest.resolve()
        manifest_id = manifest.relative_to(ROOT).as_posix()
        rows = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("A manifest must be a list")
        for row in rows:
            if categories and row.get("category") not in categories:
                continue
            audio = (manifest.parent / row["audio"]).resolve()
            audio.relative_to(manifest.parent)  # reject path traversal / symlinks out
            if not isinstance(row.get("reference"), str):
                raise ValueError("Every clip needs a written reference")
            clip_id = manifest_id + "::" + row["audio"]
            if clip_id in seen:
                raise ValueError("Duplicate corpus clip ID")
            seen.add(clip_id)
            with wave.open(str(audio), "rb") as w:
                if (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getcomptype()) != (SR, 1, 2, "NONE"):
                    raise ValueError("Trial audio must be PCM 16 kHz mono int16 WAV")
                seconds = w.getnframes() / SR
                if seconds <= 0 or seconds > 3600:
                    raise ValueError("Clip length must be between 0 and 3600 seconds")
            entries.append(dict(row, clip_id=clip_id, audio_sha256=sha256(audio),
                                duration_s=seconds, _path=audio))
    if not entries:
        raise ValueError("No clips selected")
    # References, terms, names and categories are frozen too, not just audio.
    identity = [{k: v for k, v in e.items() if k != "_path"} for e in entries]
    return entries, canonical_hash(identity)


def verify_model(path: Path) -> dict:
    path = path.resolve()
    record = json.loads((path / "integrity.json").read_text(encoding="utf-8"))
    if record.get("model_id") != MODEL_ID or record.get("revision") != MODEL_REVISION:
        raise ValueError("Unexpected model source/revision")
    hashes = record.get("sha256", {})
    if set(hashes) != set(MODEL_FILES):
        raise ValueError("Incomplete model integrity record")
    if any(p.is_file() and p.name not in (*MODEL_FILES, "integrity.json") for p in path.iterdir()):
        raise ValueError("Unexpected model file; use a clean allowlisted snapshot")
    for name, expected in hashes.items():
        if sha256(path / name) != expected:
            raise ValueError("Model integrity mismatch: " + name)
    return record


def source_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def source_hashes() -> dict:
    paths = list((ROOT / "src").glob("*.py")) + list((ROOT / "src" / "vocab").glob("*.txt"))
    paths += list((ROOT / "src" / "prompts").glob("*.txt"))
    paths += [ROOT / "scripts" / name for name in (
        "asr_trial_common.py", "trial_asr.py", "score_asr_trial.py", "medasr_native_format.py",
        "medasr_decoder_trial.py", "medasr_ctc_decoder.py", "prepare_medasr_lm.py",
        "whisper_accuracy_ablation.py") if (ROOT / "scripts" / name).exists()]
    return {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(paths)}
