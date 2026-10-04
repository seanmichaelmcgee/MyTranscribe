"""Opt-in window-length trial using the unchanged app replay and engine.

Overrides only the chunk target in this process. Writes the override and this
adapter's checksum into every checkpoint, before marking the run complete.
"""
import argparse
from pathlib import Path

from asr_trial_common import ROOT, sha256, source_hashes
import trial_asr


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-seconds", type=int, choices=(20, 30), default=30)
    args, replay_args = parser.parse_known_args(argv)
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    import chunked_transcriber
    original_transcriber = chunked_transcriber.ChunkedTranscriber
    original_write = trial_asr.write_json
    adapter_hash = sha256(Path(__file__))
    frozen_sources = source_hashes()

    def transcriber(*positional, **kwargs):
        kwargs["chunk_target_s"] = float(args.chunk_seconds)
        return original_transcriber(*positional, **kwargs)

    def checkpoint(path, record):
        if record.get("completed") and (source_hashes() != frozen_sources or sha256(Path(__file__)) != adapter_hash):
            raise ValueError("Source changed during chunk-window trial")
        record["chunk_target_s"] = args.chunk_seconds
        record["config"]["chunk_target_s"] = args.chunk_seconds
        record["config"]["chunk_override_source_sha256"] = adapter_hash
        original_write(path, record)

    chunked_transcriber.ChunkedTranscriber = transcriber
    trial_asr.write_json = checkpoint
    try:
        return trial_asr.main(replay_args)
    finally:
        chunked_transcriber.ChunkedTranscriber = original_transcriber
        trial_asr.write_json = original_write


if __name__ == "__main__":
    raise SystemExit(main())
