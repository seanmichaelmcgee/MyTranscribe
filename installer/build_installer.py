"""
build_installer.py — build MyTranscribe Medical as a Windows installer for PCs without an
NVIDIA graphics card (processor only). Nothing is downloaded: it packs this PC's own Python,
the packages the app needs (no NVIDIA libraries), the app and the chosen speech model.

    python installer/build_installer.py --model C:\\path\\to\\faster-whisper-small.en [--model ...]
                                        [--version 2026.11.19] [--out dist]

Run it with the app's environment (the venv the tests use): that is where the packages are
copied from. Steps, each in its own function:

  stage()     dist/stage/: python/ (runtime + site-packages), src/, models/, NOTICE
  zip_stage() dist/payload.zip
  compile()   installer/Setup.cs -> dist/setup_stub.exe (Windows' own C# compiler, .NET 4.8)
  join()      stub + payload + trailer -> dist/MyTranscribe-Medical-Setup-<version>.exe

The installer itself (what it does on the user's PC) is described in installer/README.md.
"""

import argparse
import compileall
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement

REPO = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
CSC = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
MAGIC = b"MTSETUP1"

# What the app imports, as installed distributions; their requirements are followed.
ROOTS = ["faster-whisper", "PyQt6", "PyAudio", "pynput", "rapidfuzz", "jellyfish", "wordfreq", "psutil"]
# Never packed: the NVIDIA libraries (a processor-only build), test tools, and big packages only
# imported by tools the app never runs (onnxruntime's sympy is for model conversion).
SKIP = re.compile(r"^(nvidia-.*|torch|triton|pytest|pip|sympy|mpmath|pyinstaller.*)$", re.I)
# Parts of Qt the app does not use (it needs QtCore, QtGui, QtWidgets and SVG for one icon).
QT_DROP = re.compile(r"(?i)^(qt6(quick|qml|pdf|designer|multimedia|web|positioning|sensors|3d|bluetooth|nfc|"
                     r"serialport|test|sql|location|charts|datavis|graphs|spatial|texttospeech|virtualkeyboard|"
                     r"remoteobjects|scxml|statemachine|shadertools|lottie|help|uitools|opengl|openglwidgets|"
                     r"labs|httpserver|websockets|network|printsupport|xml)\w*\.dll|opengl32sw\.dll|"
                     r"d3dcompiler_\d+\.dll|(qt)?(quick|qml|pdf|designer|multimedia|web|3d|sql|location|"
                     r"positioning|sensors|charts|help|bluetooth|nfc|serialport|test|texttospeech|"
                     r"virtualkeyboard|remoteobjects|scxml|statemachine|spatial|datavis|graphs|lottie|"
                     r"httpserver|websockets|network|printsupport|opengl|openglwidgets|uitools|xml)\w*\.(pyd|pyi))$")
QT_KEEP_DIRS = {"platforms", "styles", "imageformats", "iconengines"}
STDLIB_DROP = {"test", "idlelib", "tkinter", "turtledemo", "ensurepip", "site-packages", "__pycache__",
               "lib2to3", "venv", "pydoc_data"}
DLLS_DROP = re.compile(r"(?i)^(_tkinter\.pyd|tcl\d+t?\.dll|tk\d+t?\.dll|_test\w*\.pyd|xxlimited.*)$")
VC_RUNTIME = ("msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll", "vcruntime140.dll", "vcruntime140_1.dll",
              "concrt140.dll", "vcomp140.dll")


# ── Which packages ───────────────────────────────────────────────────────────
def closure(roots):
    """Installed distributions the roots need, following requirements (no extras)."""
    env = default_environment()
    env["extra"] = ""
    seen, todo = {}, list(roots)
    while todo:
        name = todo.pop()
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in seen or SKIP.match(key):
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            print(f"  (not installed, skipped: {name})")
            continue
        seen[key] = dist
        for spec in dist.requires or []:
            req = Requirement(spec)
            if req.marker is None or req.marker.evaluate(env):
                todo.append(req.name)
    return seen


def copy_dist(dist, site: Path) -> int:
    """Copy one distribution's files (from its RECORD) into site; returns bytes copied."""
    base = Path(dist.locate_file(""))
    total = 0
    for f in dist.files or []:
        rel = Path(str(f))
        if rel.parts and rel.parts[0] in ("..",) or "__pycache__" in rel.parts or rel.suffix == ".pyc":
            continue
        # Packages' own tests and developer tools: never imported by the app, and they hold the
        # longest file paths (a deep install folder must stay under Windows' 260 characters).
        if "tests" in rel.parts or rel.parts[:2] == ("onnxruntime", "tools"):
            continue
        src = base / rel
        if not src.is_file():
            continue
        parts = [p for p in rel.parts]
        if parts[0] == "PyQt6" and _qt_drop(rel):
            continue
        dst = site / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        total += src.stat().st_size
    return total


def _qt_drop(rel: Path) -> bool:
    name = rel.name
    if QT_DROP.match(name):
        return True
    parts = rel.parts
    if len(parts) > 3 and parts[1] == "Qt6" and parts[2] == "plugins" and parts[3] not in QT_KEEP_DIRS:
        return True
    if len(parts) > 2 and parts[1] == "Qt6" and parts[2] in ("qml", "translations", "resources"):
        return True
    return False


def third_party(dists, models) -> str:
    """What is bundled and under which licence, as each package declares it."""
    lines = ["MyTranscribe Medical bundles the following software and data.", "",
             f"Python {sys.version.split()[0]} (Python Software Foundation License): python/LICENSE.txt", ""]
    for key, dist in sorted(dists.items()):
        meta = dist.metadata
        lic = (meta.get("License-Expression") or meta.get("License") or "").strip().splitlines()
        classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License")]
        text = lic[0][:100] if lic and len(lic[0]) < 100 else "; ".join(classifiers) or "see the package"
        lines.append(f"{meta['Name']} {meta['Version']}: {text}")
    lines += ["", "Speech models (OpenAI Whisper weights, MIT; CTranslate2 conversions):"]
    lines += [f"  {Path(m).name}: {(Path(m) / 'SOURCE.txt').read_text(encoding='utf-8').strip()}"
              if (Path(m) / "SOURCE.txt").is_file() else f"  {Path(m).name}" for m in models]
    return "\n".join(lines) + "\n"


# ── Stage ────────────────────────────────────────────────────────────────────
def stage(out: Path, models, version: str) -> Path:
    st = out / "stage"
    if st.exists():
        shutil.rmtree(st)
    py = st / "python"
    base = Path(sys.base_prefix)
    print(f"Python runtime from {base}")
    py.mkdir(parents=True)
    for name in ("python.exe", "pythonw.exe", "python3.dll", f"python{sys.version_info.major}{sys.version_info.minor}.dll",
                 "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"):
        if (base / name).is_file():
            shutil.copy2(base / name, py / name)
    # The C++ runtime many packages need, next to python.exe so a PC without the
    # Visual C++ redistributable still loads them.
    system32 = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
    for name in VC_RUNTIME:
        if not (py / name).exists() and (system32 / name).is_file():
            shutil.copy2(system32 / name, py / name)
    (py / "DLLs").mkdir()
    for f in (base / "DLLs").iterdir():
        if f.is_file() and not DLLS_DROP.match(f.name):
            shutil.copy2(f, py / "DLLs" / f.name)

    def ignore(folder, names):
        return [n for n in names if n in STDLIB_DROP or n.endswith(".pyc")]
    shutil.copytree(base / "Lib", py / "Lib", ignore=ignore)
    site = py / "Lib" / "site-packages"
    site.mkdir()
    dists = closure(ROOTS)
    sizes = {}
    for key, dist in sorted(dists.items()):
        sizes[key] = copy_dist(dist, site)
    (st / "THIRD-PARTY.txt").write_text(third_party(dists, models), encoding="utf-8")
    print("Packages:", ", ".join(f"{k} {v / 1e6:.0f} MB" for k, v in sorted(sizes.items(), key=lambda kv: -kv[1])))
    tag = f"python{sys.version_info.major}{sys.version_info.minor}"
    # Isolated: only these folders, whatever is installed or set on the PC.
    (py / f"{tag}._pth").write_text("Lib\nDLLs\nLib\\site-packages\n..\\src\nimport site\n", encoding="utf-8")

    def ignore_src(folder, names):
        return [n for n in names if n in ("__pycache__",) or n.endswith(".pyc")]
    shutil.copytree(REPO / "src", st / "src", ignore=ignore_src)
    for m in models:
        m = Path(m)
        shutil.copytree(m, st / "models" / m.name)
    for name in ("LICENSE.txt", "NOTICE.md"):
        if (REPO / name).is_file():
            shutil.copy2(REPO / name, st / name)
    shutil.copy2(HERE / "selftest.py", st / "selftest.py")
    info = {"version": version, "device": "cpu", "models": [Path(m).name for m in models],
            "python": sys.version.split()[0]}
    (st / "build_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print("Compiling Python files ...")
    compileall.compile_dir(str(st), quiet=1, workers=0)
    total = sum(f.stat().st_size for f in st.rglob("*") if f.is_file())
    print(f"Staged {total / 1e9:.2f} GB in {st}")
    return st


# ── Payload, stub, installer ─────────────────────────────────────────────────
def zip_stage(st: Path, out: Path) -> Path:
    payload = out / "payload.zip"
    files = [f for f in st.rglob("*") if f.is_file()]
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for f in files:
            # Model weights hardly compress: store them, so installing is quicker.
            kind = zipfile.ZIP_STORED if f.suffix == ".bin" else zipfile.ZIP_DEFLATED
            z.write(f, f.relative_to(st).as_posix(), compress_type=kind)
    print(f"Payload {payload.stat().st_size / 1e9:.2f} GB ({len(files)} files)")
    return payload


def compile_stub(out: Path, icon: Path) -> Path:
    exe = out / "setup_stub.exe"
    refs = ["System.dll", "System.Core.dll", "System.Drawing.dll", "System.Windows.Forms.dll",
            "System.IO.Compression.dll", "System.IO.Compression.FileSystem.dll"]
    cmd = [str(CSC), "/nologo", "/target:winexe", "/optimize+", f"/out:{exe}", f"/win32icon:{icon}",
           f"/resource:{icon},MyTranscribe.ico", f"/resource:{icon.with_suffix('.png')},MyTranscribe.png",
           f"/win32manifest:{HERE / 'Setup.manifest'}"] + [f"/reference:{r}" for r in refs] + [str(HERE / "Setup.cs")]
    subprocess.run(cmd, check=True)
    return exe


def join(stub: Path, payload: Path, out: Path, version: str) -> Path:
    setup = out / f"MyTranscribe-Medical-Setup-{version}.exe"
    offset = stub.stat().st_size
    with open(setup, "wb") as w:
        for part in (stub, payload):
            with open(part, "rb") as r:
                shutil.copyfileobj(r, w, 16 << 20)
        w.write(struct.pack("<q", offset) + MAGIC)
    print(f"Installer {setup} ({setup.stat().st_size / 1e9:.2f} GB)")
    return setup


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", action="append", required=True, help="a faster-whisper model folder to include")
    ap.add_argument("--version", default="dev")
    ap.add_argument("--out", type=Path, default=REPO / "dist")
    ap.add_argument("--skip-stage", action="store_true", help="reuse dist/stage")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    st = args.out / "stage" if args.skip_stage else stage(args.out, args.model, args.version)
    payload = zip_stage(st, args.out)
    stub = compile_stub(args.out, REPO / "src" / "assets" / "mytranscribe.ico")
    join(stub, payload, args.out, args.version)


if __name__ == "__main__":
    main()
