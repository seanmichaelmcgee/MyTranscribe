"""Download only the official pinned safetensors snapshot; never takes trial audio."""
import argparse
import os
import sys
from pathlib import Path

from asr_trial_common import MODEL_FILES, MODEL_ID, MODEL_REVISION, ROOT, sha256, write_json


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "models_medasr" / MODEL_REVISION)
    ap.add_argument("--ca-bundle", type=Path)
    args = ap.parse_args()
    out = args.out.resolve()
    out.relative_to(ROOT / "models_medasr")
    if args.ca_bundle:
        os.environ["SSL_CERT_FILE"] = str(args.ca_bundle.resolve(strict=True))
        os.environ["REQUESTS_CA_BUNDLE"] = os.environ["SSL_CERT_FILE"]
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"  # use TLS/CA-verified standard HTTP download
    from huggingface_hub import HfApi, get_token, hf_hub_download
    from huggingface_hub.errors import GatedRepoError
    try:
        # This also verifies access before creating a partial model directory.
        hf_hub_download(MODEL_ID, "config.json", revision=MODEL_REVISION)
        info = HfApi().model_info(MODEL_ID, revision=MODEL_REVISION, files_metadata=True)
        upstream_weight_hash = next(f.lfs.sha256 for f in info.siblings if f.rfilename == "model.safetensors")
        out.mkdir(parents=True, exist_ok=True)
        for name in MODEL_FILES:
            downloaded = Path(hf_hub_download(MODEL_ID, name, revision=MODEL_REVISION))
            # Copy resolved cache data: no executable repo files, no cache symlinks.
            import shutil
            shutil.copyfile(downloaded, out / name)
        hashes = {name: sha256(out / name) for name in MODEL_FILES}
        if hashes["model.safetensors"] != upstream_weight_hash:
            raise ValueError("Weight checksum does not match the official LFS metadata")
        write_json(out / "integrity.json", dict(model_id=MODEL_ID, revision=MODEL_REVISION,
                                               sha256=hashes, official_weight_sha256=upstream_weight_hash))
        print("Official snapshot verified. Inference is offline.")
        return 0
    except GatedRepoError:
        if get_token():
            print("A local credential is present, but Google has denied this model download.")
            print("Review/accept access conditions at https://huggingface.co/google/medasr using the same account.")
            print("If access is already granted, check that this credential permits gated-model downloads.")
        else:
            print("Model access required: review conditions at https://huggingface.co/google/medasr,")
            print("then run venvmedasr\\Scripts\\hf.exe auth login locally. Do not paste tokens into chat.")
        return 2


if __name__ == "__main__":
    sys.exit(main())
