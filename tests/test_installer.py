"""The Windows installer build (installer/build_installer.py): the processor-only and graphics-card editions."""

import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "installer"))

import build_installer as bi  # noqa: E402


class FakeDist:
    """Just enough of importlib.metadata.Distribution: files under base, a name and a version."""

    def __init__(self, base: Path, files, name="nvidia-cublas-cu12", version="12.9.2.10"):
        self.base, self.files, self.version = base, [Path(f) for f in files], version
        self.metadata = {"Name": name, "Version": version, "License-Expression": "LicenseRef-NVIDIA-Proprietary"}
        for f in self.files:
            (base / f).parent.mkdir(parents=True, exist_ok=True)
            (base / f).write_bytes(b"x" * 10)

    def locate_file(self, path):
        return self.base / path


CUBLAS_WHEEL = ["nvidia/cublas/bin/cublas64_12.dll", "nvidia/cublas/bin/cublasLt64_12.dll",
                "nvidia/cublas/bin/nvblas64_12.dll", "nvidia/cublas/include/cublas.h",
                "nvidia_cublas_cu12-12.9.2.10.dist-info/METADATA",
                "nvidia_cublas_cu12-12.9.2.10.dist-info/licenses/License.txt"]


def test_the_processor_build_packs_no_nvidia_library():
    assert all(bi.SKIP.match(n) for n in ("nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-nvrtc-cu12"))
    assert not any(key.startswith("nvidia") for key in bi.closure(bi.ROOTS))
    assert bi.GPU_LIBS == {"nvidia-cublas-cu12": ("cublas64_12.dll", "cublasLt64_12.dll")}   # cuDNN is not needed


def test_gpu_build_copies_only_the_listed_dlls_and_the_licence(tmp_path):
    dist = FakeDist(tmp_path / "venv", CUBLAS_WHEEL)
    site = tmp_path / "site"
    sizes = bi.copy_gpu_libs({"nvidia-cublas-cu12": dist}, site)
    got = sorted(p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file())
    assert got == sorted(CUBLAS_WHEEL[:2] + CUBLAS_WHEEL[4:]) and sizes == {"nvidia-cublas-cu12": 40}
    assert bi.copy_gpu_libs({}, site) == {}                                  # the processor build
    (tmp_path / "venv" / CUBLAS_WHEEL[1]).unlink()
    with pytest.raises(SystemExit, match="cublaslt64_12.dll"):
        bi.copy_gpu_libs({"nvidia-cublas-cu12": dist}, tmp_path / "site2")


def test_third_party_names_the_nvidia_libraries_and_their_licence(tmp_path):
    dist = FakeDist(tmp_path, CUBLAS_WHEEL)
    text = bi.third_party({}, [], {"nvidia-cublas-cu12": dist})
    assert "nvidia-cublas-cu12 12.9.2.10: cublas64_12.dll, cublasLt64_12.dll" in text
    assert "CUDA Toolkit End User" in text and "nvidia_cublas_cu12-12.9.2.10.dist-info/licenses/License.txt" in text
    assert "NVIDIA" not in bi.third_party({}, [])


def _payload(tmp_path, size=1000):
    stub, payload = tmp_path / "stub.exe", tmp_path / "stage.zip"
    stub.write_bytes(b"MZ" + b"s" * 98)
    payload.write_bytes(b"PK" + b"p" * (size - 2))
    return stub, payload


def test_join_appends_the_payload_to_the_program(tmp_path):
    stub, payload = _payload(tmp_path)
    setup = bi.join(stub, payload, tmp_path, "1.0")
    assert setup.name == "MyTranscribe-Medical-Setup-1.0.exe" and not setup.with_suffix(".data").exists()
    raw = setup.read_bytes()
    assert raw[:100] == stub.read_bytes() and raw[100:-16] == payload.read_bytes()
    assert raw[-16:] == struct.pack("<q", 100) + bi.MAGIC
    assert bi.join(stub, payload, tmp_path, "1.0", gpu=True).name == "MyTranscribe-Medical-GPU-Setup-1.0.exe"


def test_join_puts_a_payload_past_windows_limit_beside_the_program(tmp_path):
    stub, payload = _payload(tmp_path)
    setup = bi.join(stub, payload, tmp_path, "1.0", gpu=True, limit=1000)
    data = tmp_path / "MyTranscribe-Medical-GPU-Setup-1.0.data"
    raw, name = setup.read_bytes(), data.name.encode()
    assert raw[:100] == stub.read_bytes() and raw[100:-16] == name
    assert raw[-16:] == struct.pack("<q", len(name)) + bi.MAGIC_DATA
    assert data.read_bytes() == payload.read_bytes() + struct.pack("<q", 0) + bi.MAGIC
    bi.join(stub, payload, tmp_path, "1.0", gpu=True)                        # fits again: one file, no stale data
    assert not data.exists()
    assert bi.ONE_FILE_LIMIT < 1 << 32


def test_the_gpu_stub_is_compiled_as_its_own_edition(tmp_path):
    seen = []
    bi.compile_stub(tmp_path, Path("icon.ico"), run=lambda cmd, check: seen.append(cmd))
    bi.compile_stub(tmp_path, Path("icon.ico"), gpu=True, run=lambda cmd, check: seen.append(cmd))
    assert "/define:GPU_EDITION" not in seen[0] and "/define:GPU_EDITION" in seen[1]
    assert seen[0][-1].endswith("Setup.cs") and seen[1][-1].endswith("Setup.cs")


@pytest.mark.skipif(not bi.CSC.is_file(), reason="needs Windows' C# compiler (.NET Framework 4.8)")
def test_setup_compiles_in_both_editions_with_their_own_apps_entry(tmp_path):
    icon = bi.REPO / "src" / "assets" / "mytranscribe.ico"
    names = {}
    for gpu in (False, True):
        out = tmp_path / ("gpu" if gpu else "cpu")
        out.mkdir()
        names[gpu] = bi.compile_stub(out, icon, gpu).read_bytes()
    key = lambda s: s.encode("utf-16-le")                                    # noqa: E731  (.NET string heap)
    assert key("MyTranscribeMedicalGPU") in names[True] and key("(graphics card)") in names[True]
    assert key("MyTranscribeMedicalGPU") not in names[False] and key("(graphics card)") not in names[False]
    assert key(r"Uninstall\MyTranscribeMedical") in names[False]


def test_updates_and_reused_stages_must_be_the_same_edition(tmp_path):
    base = tmp_path / "stage"
    (base / "python" / "Lib" / "site-packages").mkdir(parents=True)
    (base / "build_info.json").write_text(json.dumps({"version": "1.0", "device": "cuda"}), encoding="utf-8")
    assert bi.check_edition(base, "cuda")["version"] == "1.0"
    with pytest.raises(SystemExit, match="graphics-card edition, not the processor-only one"):
        bi.stage_update(tmp_path, "1.0.1", base, "cpu")
    (base / "build_info.json").write_text(json.dumps({"version": "1.0"}), encoding="utf-8")     # older builds
    with pytest.raises(SystemExit, match="processor-only edition, not the graphics-card one"):
        bi.check_edition(base, "cuda")
    (base / "build_info.json").write_text(json.dumps({"version": "1.0", "device": "any"}), encoding="utf-8")
    assert bi.check_edition(base, "any")["version"] == "1.0"
    with pytest.raises(SystemExit, match="every-PC edition, not the processor-only one"):
        bi.check_edition(base, "cpu")


def test_every_pc_build_packs_the_nvidia_libraries_under_the_usual_name(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(bi, "stage", lambda out, models, version, device: seen.update(device=device) or out / "st")
    monkeypatch.setattr(bi, "zip_stage", lambda st, out: out / "p.zip")
    monkeypatch.setattr(bi, "compile_stub", lambda out, icon, gpu: seen.update(gpu_stub=gpu) or out / "stub")
    monkeypatch.setattr(bi, "join", lambda *a: seen.update(join=a))
    bi.main(["--every-pc", "--model", "small.en", "--version", "1.0", "--out", str(tmp_path)])
    assert seen["device"] == "any" and seen["gpu_stub"] is False and seen["join"][-1] is False   # "MyTranscribe Medical"
    bi.main(["--gpu", "--model", "large-v3", "--version", "1.0", "--out", str(tmp_path)])
    assert seen["device"] == "cuda" and seen["gpu_stub"] is True and seen["join"][-1] is True
    bi.main(["--model", "small.en", "--version", "1.0", "--out", str(tmp_path)])
    assert seen["device"] == "cpu" and seen["gpu_stub"] is False
    with pytest.raises(SystemExit):
        bi.main(["--gpu", "--every-pc", "--model", "x", "--out", str(tmp_path)])


def test_only_the_every_pc_build_takes_truststore_for_its_download():
    assert "truststore" in bi.roots("any")
    assert "truststore" not in bi.roots("cpu") and "truststore" not in bi.roots("cuda")   # they download nothing
    assert bi.roots("cpu") == bi.ROOTS                                                  # processor-only: unchanged
