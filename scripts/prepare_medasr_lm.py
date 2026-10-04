"""Prepare Google's pinned text ARPA LM for a local, dependency-free decoder trial.

Only the allowlisted official data file is downloaded. The indexed SQLite data
contains probabilities, not executable objects. No recordings or references are read.
"""
import argparse
import lzma
import math
import os
import sqlite3
from pathlib import Path

from asr_trial_common import MODEL_ID, MODEL_REVISION, ROOT, sha256, write_json

LM_FILE = "lm_6.arpa.xz"
LM_SHA256 = "bf0119b19ba8811fb91b67c7374fa02baa6a0f0660d1235f2192f4d6874c2b3b"
LM_SIZE = 240317220
LM_ROOT = ROOT / "models_medasr" / "language_model" / MODEL_REVISION


def build_index(source, target):
    """Stream bounded ARPA text into an indexed read-only probability table."""
    if sha256(source) != LM_SHA256:
        raise ValueError("Official ARPA checksum mismatch")
    temporary = target.with_suffix(".building.sqlite")
    if temporary.exists():
        raise ValueError("Unfinished index exists; inspect before restarting")
    db = sqlite3.connect(temporary)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    db.execute("PRAGMA cache_size=-65536")
    db.execute("CREATE TABLE grams (key TEXT PRIMARY KEY, probability REAL NOT NULL, backoff REAL NOT NULL) WITHOUT ROWID")
    db.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    order, seen, total_bytes, batch, counts, expected = 0, 0, 0, [], {}, {}
    try:
        with lzma.open(source, "rt", encoding="utf-8") as stream:
            for line in stream:
                total_bytes += len(line.encode("utf-8"))
                if total_bytes > 4 * 1024**3 or len(line) > 8192:
                    raise ValueError("ARPA size/line bound exceeded")
                line = line.strip()
                if line.startswith("ngram "):
                    left, right = line[6:].split("=")
                    expected[int(left)] = int(right)
                    continue
                if line.startswith("\\"):
                    order = int(line[1:].split("-")[0]) if line.endswith("-grams:") else 0
                    if order > 6:
                        raise ValueError("Unsupported ARPA order")
                    continue
                if not order or not line:
                    continue
                fields = line.split()
                if len(fields) not in (order + 1, order + 2):
                    raise ValueError("Malformed ARPA row")
                probability = float(fields[0])
                backoff = float(fields[-1]) if len(fields) == order + 2 else 0.0
                if not math.isfinite(probability) or not math.isfinite(backoff):
                    raise ValueError("Nonfinite ARPA value")
                batch.append((" ".join(fields[1:order + 1]), probability, backoff))
                counts[order] = counts.get(order, 0) + 1
                seen += 1
                if len(batch) >= 10000:
                    db.executemany("INSERT INTO grams VALUES (?,?,?)", batch)
                    batch.clear()
                    if seen % 1000000 == 0:
                        print(f"Indexed {seen:,} official ngrams", flush=True)
        db.executemany("INSERT INTO grams VALUES (?,?,?)", batch)
        if counts != expected or not counts:
            raise ValueError("ARPA declared/actual counts differ")
        db.executemany("INSERT INTO metadata VALUES (?,?)", [("arpa_sha256", LM_SHA256), ("revision", MODEL_REVISION)])
        db.commit()
    finally:
        db.close()
    os.replace(temporary, target)
    write_json(target.with_suffix(".integrity.json"), dict(model_id=MODEL_ID, revision=MODEL_REVISION,
        arpa_sha256=LM_SHA256, index_sha256=sha256(target), ngrams=counts, uncompressed_bytes=total_bytes))
    print(f"Verified local LM index ready: {seen:,} ngrams", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ca-bundle", type=Path)
    args = parser.parse_args()
    if args.ca_bundle:
        os.environ["SSL_CERT_FILE"] = str(args.ca_bundle.resolve(strict=True))
        os.environ["REQUESTS_CA_BUNDLE"] = os.environ["SSL_CERT_FILE"]
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    from huggingface_hub import hf_hub_download
    import shutil
    LM_ROOT.mkdir(parents=True, exist_ok=True)
    archive = LM_ROOT / LM_FILE
    if not archive.exists():
        cached = hf_hub_download(MODEL_ID, LM_FILE, revision=MODEL_REVISION)
        shutil.copyfile(cached, archive)
    if archive.stat().st_size != LM_SIZE or sha256(archive) != LM_SHA256:
        raise ValueError("Official LM size/hash mismatch")
    target = LM_ROOT / "ngrams.sqlite"
    if target.exists():
        raise ValueError("Index already exists; verify and reuse it rather than overwrite")
    build_index(archive, target)


if __name__ == "__main__":
    main()
