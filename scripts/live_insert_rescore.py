"""
live_insert_rescore.py: re-type saved live_insert_bench runs with the current
live_insert rules (no recognition needed) and count where the typed text still
differs from the text copied at Stop.

    python scripts/live_insert_rescore.py results_1060/live_insert/chunk30_personal.json ...
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import dictation_reliability as dr                 # noqa: E402
from live_insert_bench import typed_text           # noqa: E402


def main(paths):
    profile = dr.PROFILES["personal"]
    for path in paths:
        rows = json.loads(Path(path).read_text(encoding="utf-8"))["rows"]
        differ = words = 0
        for r in rows:
            typed = typed_text([p for p in r["raw_pieces"] if p], profile)
            if typed.strip() != r["final"].strip():
                differ += 1
                words += dr.word_edits(r["final"], typed)
        print(f"{Path(path).stem:28s} typed differs from copied in {differ} of {len(rows)} recordings "
              f"({words} word differences)")


if __name__ == "__main__":
    main(sys.argv[1:])
