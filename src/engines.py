"""
engines.py — the speech recognisers the app can use, and what each needs.

Options -> Speech model picks one. Whisper (faster-whisper) is the default and
the only one the standard install provides; the others are optional and appear
as unavailable, with the reason, until their packages and model are present.

Nothing is downloaded behind the user's back: the app runs with the Hugging
Face hub offline. When a model is not on the PC yet, loading raises
ModelNotDownloaded and the window asks before fetching it (see MODEL_NOTES for
where it comes from, its size and its licence). MedASR cannot be fetched that
way: Google gates it behind terms each user accepts with their own account.
"""

import importlib.util
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("engines")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT = "whisper"
# What Options -> Recogniser offers. Parakeet and Canary stay usable for trials
# (MYTRANSCRIBE_ENGINE, the benchmark scripts) but were clearly behind on medical dictation.
OFFERED = ("whisper", "medasr")


@dataclass(frozen=True)
class EngineInfo:
    name: str
    label: str
    needs: Tuple[str, ...]        # importable packages
    source: str                   # where the model comes from
    size: str
    licence: str
    note: str = ""


ENGINES = {
    "whisper": EngineInfo(
        "whisper", "Whisper large-v3 (recommended)", ("faster_whisper",),
        "Hugging Face: Systran/faster-whisper-large-v3 (or -large-v3-turbo for Fast)", "about 3 GB (turbo 1.6 GB)",
        "MIT (OpenAI Whisper weights, Systran conversion); no account or acceptance needed",
        "Most accurate here; uses your vocabulary. 'Accuracy' below chooses large-v3 or turbo."),
    "medasr": EngineInfo(
        "medasr", "MedASR (Google, medical dictation; very fast)", ("torch", "transformers"),
        "Hugging Face: google/medasr (gated)", "about 0.4 GB, plus PyTorch (about 2.5 GB)",
        "Health AI Developer Foundations terms: each user must accept them on huggingface.co/google/medasr "
        "with their own account and sign in before downloading",
        "Licence terms must be accepted before use: Google only releases this model to people who have "
        "accepted its Health AI Developer Foundations terms themselves. Good drug names, weak on people's "
        "names and the first words. Set up with scripts\\setup_medasr.ps1 and scripts\\download_medasr.py "
        "(docs/MEDASR_TRIAL.md)."),
    "parakeet": EngineInfo(
        "parakeet", "Parakeet 0.6B v2 (NVIDIA; fastest)", ("onnx_asr", "onnxruntime"),
        "Hugging Face: istupakov/parakeet-tdt-0.6b-v2-onnx (community ONNX export of nvidia/parakeet-tdt-0.6b-v2)",
        "about 2.5 GB", "CC BY 4.0 (attribution to NVIDIA); no account or acceptance needed",
        "General English; no medical vocabulary. Needs: pip install onnx-asr[hub] onnxruntime-gpu[cuda,cudnn]."),
    "canary": EngineInfo(
        "canary", "Canary 1B v2 (NVIDIA)", ("onnx_asr", "onnxruntime"),
        "Hugging Face: istupakov/canary-1b-v2-onnx (community ONNX export of nvidia/canary-1b-v2)",
        "about 4 GB", "CC BY 4.0 (attribution to NVIDIA); no account or acceptance needed",
        "General English; no medical vocabulary. Needs: pip install onnx-asr[hub] onnxruntime-gpu[cuda,cudnn]."),
}


class ModelNotDownloaded(RuntimeError):
    """The chosen model is not on this PC and the hub is offline."""

    def __init__(self, engine: str, detail: str = "") -> None:
        super().__init__(f"The {ENGINES[engine].label} model is not on this PC yet. {detail}".strip())
        self.engine = engine


def medasr_snapshot(env: Optional[dict] = None) -> Optional[Path]:
    """The verified local MedASR snapshot folder, or None."""
    env = os.environ if env is None else env
    override = env.get("MYTRANSCRIBE_MEDASR_DIR", "").strip()
    folders = [Path(override)] if override else sorted((ROOT / "models_medasr").glob("*/"))
    for folder in folders:
        if (folder / "model.safetensors").is_file() and (folder / "integrity.json").is_file():
            return folder
    return None


def availability(name: str, find_spec=importlib.util.find_spec, env: Optional[dict] = None) -> Tuple[bool, str]:
    """(usable now?, why not). A missing model that can be downloaded still counts as usable."""
    info = ENGINES.get(name)
    if info is None:
        return False, "unknown recogniser"
    missing = [p for p in info.needs if find_spec(p) is None]
    if missing:
        return False, "not installed: " + ", ".join(missing)
    if name == "medasr" and medasr_snapshot(env) is None:
        return False, "model not downloaded (needs your own Hugging Face sign-in; see docs/MEDASR_TRIAL.md)"
    return True, ""


def _is_missing_model(exc: BaseException) -> bool:
    names = {c.__name__ for c in type(exc).__mro__}
    text = str(exc).lower()
    return bool(names & {"LocalEntryNotFoundError", "OfflineModeIsEnabled"}) or (
        "offline" in text and ("hub" in text or "cannot find" in text or "outgoing traffic" in text))


def build(name: str = DEFAULT, accurate: bool = True, allow_download: bool = False):
    """
    Load and warm up the recogniser `name`. With allow_download the hub is
    reachable for this one load (the user said yes); otherwise it stays offline.
    """
    if name not in ENGINES:
        logger.warning("Unknown recogniser %r; using %s", name, DEFAULT)
        name = DEFAULT
    ok, why = availability(name)
    if not ok:
        raise RuntimeError(f"{ENGINES[name].label} cannot be used: {why}")
    previous = os.environ.get("HF_HUB_OFFLINE")
    try:
        if allow_download:
            os.environ["HF_HUB_OFFLINE"] = "0"
            _use_system_certificates()
        else:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        _hub_offline(not allow_download and os.environ["HF_HUB_OFFLINE"] == "1")
        try:
            return _build(name, accurate)
        except Exception as exc:
            if not allow_download and _is_missing_model(exc):
                raise ModelNotDownloaded(name) from exc
            raise
    finally:
        if allow_download:
            if previous is None:
                os.environ["HF_HUB_OFFLINE"] = "1"
            else:
                os.environ["HF_HUB_OFFLINE"] = previous
            _hub_offline(os.environ["HF_HUB_OFFLINE"] == "1")


def _build(name: str, accurate: bool):
    if name == "whisper":
        from fw_engine import FasterWhisperEngine, register_cuda_dll_dirs
        from hw_profile import choose_config, detect_hardware
        register_cuda_dll_dirs()                 # before ctranslate2 touches CUDA (Windows); harmless to repeat
        cfg = choose_config(detect_hardware(), accurate=accurate)
        logger.info("Engine config: model=%s device=%s compute=%s threads=%d (%s)",
                    cfg.model, cfg.device, cfg.compute_type, cfg.cpu_threads, cfg.reason)
        engine = FasterWhisperEngine(cfg)
    elif name == "medasr":
        from medasr_engine import MedASREngine
        import torch
        engine = MedASREngine(medasr_snapshot(), device="cuda" if torch.cuda.is_available() else "cpu")
    else:
        from onnx_engine import OnnxAsrEngine
        engine = OnnxAsrEngine(name)
    logger.info("Recogniser: %s", ENGINES[name].label)
    if hasattr(engine, "warmup"):
        engine.warmup()
    return engine


def _hub_offline(offline: bool) -> None:
    """huggingface_hub reads HF_HUB_OFFLINE once, at import: keep its copy in step."""
    try:
        from huggingface_hub import constants
        constants.HF_HUB_OFFLINE = offline
    except Exception:
        pass


def _use_system_certificates() -> None:
    """Networks that re-sign HTTPS need the Windows certificate store (optional truststore package)."""
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:
        pass
