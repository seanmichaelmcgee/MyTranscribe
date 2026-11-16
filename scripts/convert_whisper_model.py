"""
Fetch a fine-tuned Whisper model from Hugging Face and convert it for faster-whisper.

The app's recogniser is faster-whisper (CTranslate2), which reads its own model
format. A Whisper model published in the usual transformers format (safetensors)
is downloaded once and converted here; nothing else in the app changes.

    convert_whisper_model.py --repo cdli/whisper-large-v3-swahili-afrivoice-cv --language sw

writes models_whisper/<language>/ (ignored by git), which the app uses when that
dictation language is chosen. Needs the optional environment with torch and
transformers (requirements-engines.txt). Only weight and tokenizer files are
fetched (safetensors: no executable code); read the model's licence first.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = ["*.safetensors", "*.json", "merges.txt", "README.md"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", required=True, help="Hugging Face model id")
    ap.add_argument("--language", required=True, help="dictation language code the model is for, e.g. sw")
    ap.add_argument("--revision", default=None)
    ap.add_argument("--quantization", default="int8_float16")
    args = ap.parse_args(argv)

    from huggingface_hub import snapshot_download
    out = ROOT / "models_whisper" / args.language
    if (out / "model.bin").is_file():
        print(f"already converted: {out}")
        return 0
    source = Path(snapshot_download(args.repo, revision=args.revision, allow_patterns=PATTERNS))
    print(f"downloaded {args.repo} to {source}", flush=True)

    from transformers import WhisperProcessor
    WhisperProcessor.from_pretrained(str(source)).tokenizer.save_pretrained(str(source / "_tok"))   # tokenizer.json
    import ctranslate2
    converter = ctranslate2.converters.TransformersConverter(
        str(source), copy_files=["preprocessor_config.json"], load_as_float16=True)
    if out.exists():
        shutil.rmtree(out)
    converter.convert(str(out), quantization=args.quantization)
    tok = source / "_tok" / "tokenizer.json"
    if tok.is_file():
        shutil.copyfile(tok, out / "tokenizer.json")
    (out / "source.json").write_text(json.dumps(
        {"repo": args.repo, "revision": source.name, "quantization": args.quantization}, indent=1), encoding="utf-8")
    print(f"converted to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
