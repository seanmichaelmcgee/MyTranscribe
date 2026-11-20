"""
build_installer.py — build MyTranscribe Medical as a Windows installer. Nothing is downloaded:
it packs this PC's own Python, the packages the app needs, the app and the chosen speech models.

    python installer/build_installer.py --model C:\\path\\to\\faster-whisper-small.en [--model ...]
                                        [--version 2026.11.19] [--out dist]
    python installer/build_installer.py --update --version 2026.11.19.2     (a small update package)
    python installer/build_installer.py --gpu --model ...\\faster-whisper-large-v3 --out F:\\gpu-build

The default build is the processor-only edition: no NVIDIA libraries. --gpu builds the
graphics-card edition: it also packs the NVIDIA libraries Whisper needs on the card (GPU_LIBS)
and installs under its own name, folder and Apps entry, beside the processor-only edition.

An update package carries only src/ (about 2 MB) for PCs that already have the full install.
It is refused at build time when the packages here differ from those in the last full build
(<out>/stage), since it cannot change them; then build the full installer again. Give --gpu
for an update to the graphics-card edition.

Run it with the app's environment (the venv the tests use): that is where the packages are
copied from. Steps, each in its own function:

  stage()     <out>/stage/: python/ (runtime + site-packages), src/, models/, NOTICE
  zip_stage() <out>/stage.zip (<out>/stage_update.zip for an update package)
  compile()   installer/Setup.cs -> <out>/setup_stub.exe (Windows' own C# compiler, .NET 4.8)
  join()      stub + payload + trailer -> <out>/MyTranscribe-Medical[-GPU]-Setup-<version>.exe;
              above Windows' 4 GiB limit for a program, the payload goes into a .data file beside it

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
MAGIC = b"MTSETUP1"         # trailer: the payload (a zip) is inside this file, at the offset before it
MAGIC_DATA = b"MTSETUPD"    # trailer: the payload is in a .data file beside the program, named before it
# Windows will not start a program file of 4 GiB or more ("not a valid application for this OS
# platform"); one just under it starts (tested 2026-11-20). Larger installers ship a .data file.
ONE_FILE_LIMIT = (1 << 32) - (1 << 20)

# What the app imports, as installed distributions; their requirements are followed.
ROOTS = ["faster-whisper", "PyQt6", "PyAudio", "pynput", "rapidfuzz", "jellyfish", "wordfreq", "psutil"]
# Never followed as requirements: the NVIDIA libraries (only --gpu packs them, from GPU_LIBS),
# test tools, and big packages only imported by tools the app never runs (onnxruntime's sympy
# is for model conversion).
SKIP = re.compile(r"^(nvidia-.*|torch|triton|pytest|pip|sympy|mpmath|pyinstaller.*)$", re.I)
# The graphics-card edition (--gpu): the NVIDIA libraries CTranslate2 loads to run Whisper on the
# card, and nothing else from those wheels. Measured 2026-11-20 with large-v3 on an RTX 4070 Ti
# SUPER and the system CUDA removed from PATH: at int8_float16, float16, int8_float32 and float32
# only cuBLAS is loaded. cuDNN and NVRTC (1.2 GB more) are never loaded: CTranslate2 brings its
# own small cudnn64_9.dll loader, which stays idle, so they are left out.
GPU_LIBS = {"nvidia-cublas-cu12": ("cublas64_12.dll", "cublasLt64_12.dll")}
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
    if QT_DROP.match(name) or name.lower() == "qpdf.dll":     # the PDF image plugin needs Qt6Pdf, left out
        return True
    parts = rel.parts
    if len(parts) > 3 and parts[1] == "Qt6" and parts[2] == "plugins" and parts[3] not in QT_KEEP_DIRS:
        return True
    if len(parts) > 2 and parts[1] == "Qt6" and parts[2] in ("qml", "translations", "resources"):
        return True
    return False


def gpu_dists() -> dict:
    """The distributions GPU_LIBS names (its keys are normalised names), as installed here."""
    out = {}
    for name in GPU_LIBS:
        try:
            out[name] = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            raise SystemExit(f"--gpu needs {name} installed here (pip install {name}).")
    return out


def copy_gpu_libs(dists: dict, site: Path) -> dict:
    """Copy only the DLLs GPU_LIBS lists, and each wheel's metadata and licence; {key: bytes}."""
    sizes = {}
    for key, dist in dists.items():
        wanted = {n.lower() for n in GPU_LIBS[key]}
        base = Path(dist.locate_file(""))
        total, found = 0, set()
        for f in dist.files or []:
            rel = Path(str(f))
            if not (rel.name.lower() in wanted or rel.parts[0].endswith(".dist-info")):
                continue
            src = base / rel
            if not src.is_file():
                continue
            dst = site / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            total += src.stat().st_size
            found.add(rel.name.lower())
        missing = wanted - found
        if missing:
            raise SystemExit(f"{key} has no {', '.join(sorted(missing))} here.")
        sizes[key] = total
    return sizes


def third_party(dists, models, gpu_libs: dict = None) -> str:
    """What is bundled and under which licence, as each package declares it (gpu_libs: from gpu_dists())."""
    lines = ["MyTranscribe Medical bundles the following software and data.", "",
             f"Python {sys.version.split()[0]} (Python Software Foundation License): python/LICENSE.txt", ""]
    for key, dist in sorted(dists.items()):
        meta = dist.metadata
        lic = (meta.get("License-Expression") or meta.get("License") or "").strip().splitlines()
        classifiers = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License")]
        text = lic[0][:100] if lic and len(lic[0]) < 100 else "; ".join(classifiers) or "see the package"
        lines.append(f"{meta['Name']} {meta['Version']}: {text}")
    if gpu_libs:
        lines += ["", "NVIDIA libraries (graphics-card edition), under NVIDIA's own licence, the CUDA Toolkit End User",
                  "License Agreement (its Attachment A lists the files that may be redistributed):"]
        for key, dist in sorted(gpu_libs.items()):
            lic = next((Path(str(f)).as_posix() for f in dist.files or [] if Path(str(f)).name.lower() == "license.txt"), "")
            lines.append(f"  {dist.metadata['Name']} {dist.version}: {', '.join(GPU_LIBS[key])}"
                         + (f"; licence text: python/Lib/site-packages/{lic}" if lic else ""))
        lines.append("  The ctranslate2 package also carries NVIDIA's small cuDNN loader, cudnn64_9.dll (in every "
                     "edition); the cuDNN libraries it would load are not included, since Whisper does not use them.")
    lines += ["", "Speech models (OpenAI Whisper weights, MIT; CTranslate2 conversions):"]
    lines += [f"  {Path(m).name}: {(Path(m) / 'SOURCE.txt').read_text(encoding='utf-8').strip()}"
              if (Path(m) / "SOURCE.txt").is_file() else f"  {Path(m).name}" for m in models]
    return "\n".join(lines) + "\n"


# ── Stage ────────────────────────────────────────────────────────────────────
def stage(out: Path, models, version: str, gpu: bool = False) -> Path:
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
    gpu_libs = gpu_dists() if gpu else {}
    sizes.update(copy_gpu_libs(gpu_libs, site))
    (st / "THIRD-PARTY.txt").write_text(third_party(dists, models, gpu_libs), encoding="utf-8")
    print("Packages:", ", ".join(f"{k} {v / 1e6:.0f} MB" for k, v in sorted(sizes.items(), key=lambda kv: -kv[1])))
    tag = f"python{sys.version_info.major}{sys.version_info.minor}"
    # Isolated: only these folders, whatever is installed or set on the PC.
    (py / f"{tag}._pth").write_text("Lib\nDLLs\nLib\\site-packages\n..\\src\nimport site\n", encoding="utf-8")

    _copy_app(st)
    for m in models:
        m = Path(m)
        shutil.copytree(m, st / "models" / m.name)
    info = {"version": version, "kind": "full", "device": "cuda" if gpu else "cpu",
            "models": [Path(m).name for m in models], "python": sys.version.split()[0]}
    (st / "build_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    print("Compiling Python files ...")
    compileall.compile_dir(str(st), quiet=1, workers=0)
    total = sum(f.stat().st_size for f in st.rglob("*") if f.is_file())
    print(f"Staged {total / 1e9:.2f} GB in {st}")
    return st


def _copy_app(st: Path) -> None:
    """The app itself, as the full installer and an update package both carry it."""
    def ignore_src(folder, names):
        return [n for n in names if n in ("__pycache__",) or n.endswith(".pyc")]
    shutil.copytree(REPO / "src", st / "src", ignore=ignore_src)
    for name in ("LICENSE.txt", "NOTICE.md"):
        if (REPO / name).is_file():
            shutil.copy2(REPO / name, st / name)
    shutil.copy2(HERE / "selftest.py", st / "selftest.py")


def shipped_packages(site: Path) -> dict:
    """{distribution: version} as a staged site-packages holds them (from the .dist-info folder names)."""
    out = {}
    for d in site.glob("*.dist-info"):
        name, _, version = d.name[: -len(".dist-info")].rpartition("-")
        out[re.sub(r"[-_.]+", "-", name).lower()] = version
    return out


def check_edition(base: Path, gpu: bool) -> dict:
    """The build_info of the full build in `base`, which must be the edition asked for."""
    base_info = json.loads((base / "build_info.json").read_text(encoding="utf-8"))
    have, want = base_info.get("device", "cpu"), "cuda" if gpu else "cpu"
    if have != want:
        names = {"cuda": "graphics-card", "cpu": "processor-only"}
        raise SystemExit(f"The full build in {base} is the {names.get(have, have)} edition, not the "
                         f"{names[want]} one: check --gpu and --out.")
    return base_info


def stage_update(out: Path, version: str, base: Path, gpu: bool = False) -> Path:
    """<out>/stage_update/: src/ and the small files beside it, for an installed copy built from `base`."""
    site = base / "python" / "Lib" / "site-packages"
    if not site.is_dir():
        raise SystemExit(f"No full build in {base}: build the full installer first.")
    base_info = check_edition(base, gpu)
    here = {k: d.version for k, d in closure(ROOTS).items()}
    if gpu:
        here.update({k: d.version for k, d in gpu_dists().items()})
    shipped = shipped_packages(site)
    changed = sorted(k for k in set(here) | set(shipped) if here.get(k) != shipped.get(k))
    if changed:
        raise SystemExit("These packages differ from the full build, which an update cannot change: "
                         + ", ".join(f"{k} {shipped.get(k, '-')} -> {here.get(k, '-')}" for k in changed)
                         + ". Build the full installer instead.")
    st = out / "stage_update"
    if st.exists():
        shutil.rmtree(st)
    st.mkdir(parents=True)
    _copy_app(st)
    info = {"version": version, "kind": "update", "device": "cuda" if gpu else "cpu", "python": sys.version.split()[0],
            "base": base_info.get("version", "")}
    if info["python"] != base_info.get("python"):
        raise SystemExit(f"Python here is {info['python']}, the full build has {base_info.get('python')}.")
    (st / "build_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    compileall.compile_dir(str(st), quiet=1, workers=0)
    total = sum(f.stat().st_size for f in st.rglob("*") if f.is_file())
    print(f"Staged update {total / 1e6:.1f} MB in {st} (for full build {info['base']})")
    return st


# ── Payload, stub, installer ─────────────────────────────────────────────────
def zip_stage(st: Path, out: Path) -> Path:
    payload = out / f"{st.name}.zip"
    files = [f for f in st.rglob("*") if f.is_file()]
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        for f in files:
            # Model weights hardly compress: store them, so installing is quicker.
            kind = zipfile.ZIP_STORED if f.suffix == ".bin" else zipfile.ZIP_DEFLATED
            z.write(f, f.relative_to(st).as_posix(), compress_type=kind)
    print(f"Payload {payload.stat().st_size / 1e9:.2f} GB ({len(files)} files)")
    return payload


def compile_stub(out: Path, icon: Path, gpu: bool = False, run=subprocess.run) -> Path:
    """The installer program; --gpu compiles the graphics-card edition (its own name, folder and Apps entry)."""
    exe = out / "setup_stub.exe"
    refs = ["System.dll", "System.Core.dll", "System.Drawing.dll", "System.Windows.Forms.dll",
            "System.IO.Compression.dll", "System.IO.Compression.FileSystem.dll"]
    cmd = [str(CSC), "/nologo", "/target:winexe", "/optimize+", f"/out:{exe}", f"/win32icon:{icon}",
           f"/resource:{icon},MyTranscribe.ico", f"/resource:{icon.with_suffix('.png')},MyTranscribe.png",
           f"/win32manifest:{HERE / 'Setup.manifest'}"] + [f"/reference:{r}" for r in refs]
    if gpu:
        cmd.append("/define:GPU_EDITION")
    run(cmd + [str(HERE / "Setup.cs")], check=True)
    return exe


def join(stub: Path, payload: Path, out: Path, version: str, kind: str = "Setup", gpu: bool = False,
         limit: int = ONE_FILE_LIMIT) -> Path:
    """
    One program: stub + payload + trailer (offset, MAGIC). If that would reach Windows' limit for a
    program file, the program is stub + data file name + trailer (name length, MAGIC_DATA), and
    the payload goes into <name>.data beside it (payload + trailer with offset 0).
    """
    setup = out / f"MyTranscribe-Medical-{'GPU-' if gpu else ''}{kind}-{version}.exe"
    data = setup.with_suffix(".data")
    offset = stub.stat().st_size
    one_file = offset + payload.stat().st_size + 16 < limit
    for old in (setup, data):
        if old.exists():
            old.unlink()
    with open(setup, "wb") as w:
        with open(stub, "rb") as r:
            shutil.copyfileobj(r, w, 16 << 20)
        if one_file:
            with open(payload, "rb") as r:
                shutil.copyfileobj(r, w, 16 << 20)
            w.write(struct.pack("<q", offset) + MAGIC)
        else:
            name = data.name.encode("utf-8")
            w.write(name + struct.pack("<q", len(name)) + MAGIC_DATA)
    if not one_file:
        with open(data, "wb") as w:
            with open(payload, "rb") as r:
                shutil.copyfileobj(r, w, 16 << 20)
            w.write(struct.pack("<q", 0) + MAGIC)
        print(f"Installer {setup} ({setup.stat().st_size / 1e6:.2f} MB) and {data.name} beside it "
              f"({data.stat().st_size / 1e9:.2f} GB; one file would pass Windows' 4 GiB limit)")
    else:
        print(f"Installer {setup} ({setup.stat().st_size / 1e9:.2f} GB)")
    return setup


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", action="append", help="a faster-whisper model folder to include (full installer)")
    ap.add_argument("--version", default="dev")
    ap.add_argument("--out", type=Path, default=REPO / "dist")
    ap.add_argument("--skip-stage", action="store_true", help="reuse dist/stage")
    ap.add_argument("--update", action="store_true",
                    help="build a small update package (src/ only) for copies installed from <out>/stage")
    ap.add_argument("--gpu", action="store_true",
                    help="the graphics-card edition: also pack the NVIDIA libraries in GPU_LIBS; it installs "
                         "beside the processor-only edition under its own name")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.update:
        st = stage_update(args.out, args.version, args.out / "stage", args.gpu)
    elif args.skip_stage:
        st = args.out / "stage"
        check_edition(st, args.gpu)
    elif args.model:
        st = stage(args.out, args.model, args.version, args.gpu)
    else:
        ap.error("--model is needed for the full installer")
    payload = zip_stage(st, args.out)
    stub = compile_stub(args.out, REPO / "src" / "assets" / "mytranscribe.ico", args.gpu)
    join(stub, payload, args.out, args.version, "Update" if args.update else "Setup", args.gpu)


if __name__ == "__main__":
    main()
