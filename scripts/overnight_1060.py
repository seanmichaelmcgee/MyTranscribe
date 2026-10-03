"""
overnight_1060.py — unattended, resumable overnight test run for the 1060 edition.

Runs every test tool in a loop until a deadline, keeps Windows awake, samples
the GPU, and keeps a machine-readable status file a monitoring Claude session
(or you) can check at any time. Only synthetic, fictional audio is used.

    venv1060\\Scripts\\python.exe scripts\\overnight_1060.py --hours 8
    venv1060\\Scripts\\python.exe scripts\\overnight_1060.py --hours 8 --out results_overnight\\run1   (resume)

Output folder (default results_overnight/<timestamp>/):
  status.json   live state: phase, current task, heartbeat, per-task results
  gpu.csv       nvidia-smi samples every 30 s (memory, utilisation, temperature)
  logs/         full stdout/stderr of every task (NNN_<task>.log)
  json/         per-task JSON results
  REPORT.md     rolling summary, rewritten after every task (read this first)

Task cycle (repeats until --hours is up):
  smoke      unit tests (first cycle only)
  bench      speed/VRAM: turbo default, beam 1, large-v3, distil-large-v3.5 (first cycle only)
  eval       accuracy: all settings x all mic profiles
  long       30 min real-time dictation through the conference-mic audio
  churn      200 start/stop cycles + silence + fault injection
  gui        20 hotkey cycles through the real window (needs an unlocked desktop session)

Extra arguments after "--" go to every engine-using tool, e.g. for a sandbox:
    python scripts/overnight_1060.py --hours 0.2 -- --model /tmp/rand-tiny --device cpu --max-new-tokens 60
"""

import argparse
import csv
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


# ── Keep Windows awake ───────────────────────────────────────────────────────
def keep_awake(on: bool) -> None:
    """Stop Windows sleeping (display may still turn off) for the duration of the run."""
    if sys.platform != "win32":
        return
    import ctypes
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED, ES_AWAYMODE_REQUIRED = 0x80000000, 0x00000001, 0x00000040
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED if on else 0)
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


# ── GPU sampler ──────────────────────────────────────────────────────────────
class GpuSampler(threading.Thread):
    FIELDS = "memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw"

    def __init__(self, path: Path, interval=30):
        super().__init__(daemon=True)
        self.path, self.interval = path, interval
        self.stop_evt = threading.Event()
        self.smi = shutil.which("nvidia-smi") or (
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
            if Path(r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe").exists() else None)
        self.max_mem = 0.0
        self.max_temp = 0.0

    def run(self):
        if not self.smi:
            return
        new = not self.path.exists()
        with self.path.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time"] + self.FIELDS.split(","))
            while not self.stop_evt.is_set():
                try:
                    out = subprocess.run([self.smi, f"--query-gpu={self.FIELDS}", "--format=csv,noheader,nounits"],
                                         capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
                    if out:
                        vals = [v.strip() for v in out[0].split(",")]
                        w.writerow([now()] + vals)
                        f.flush()
                        self.max_mem = max(self.max_mem, float(vals[0]))
                        self.max_temp = max(self.max_temp, float(vals[3]))
                except (OSError, ValueError, subprocess.SubprocessError):
                    pass
                self.stop_evt.wait(self.interval)


# ── Runner ───────────────────────────────────────────────────────────────────
class Run:
    def __init__(self, out: Path, deadline: float, engine_args, gpu: GpuSampler):
        self.out, self.deadline, self.engine_args, self.gpu = out, deadline, engine_args, gpu
        (out / "logs").mkdir(parents=True, exist_ok=True)
        (out / "json").mkdir(exist_ok=True)
        self.status_path = out / "status.json"
        if self.status_path.exists():
            self.status = json.loads(self.status_path.read_text(encoding="utf-8"))
            self.status["resumed_at"] = now()
        else:
            self.status = {"started": now(), "tasks": [], "cycle": 0}
        self.status.update(phase="running", deadline=dt.datetime.fromtimestamp(deadline).isoformat(timespec="seconds"),
                           engine_args=engine_args, pid=os.getpid())
        self.save()

    def save(self):
        self.status["heartbeat"] = now()
        self.status["gpu_max_mem_mb"] = self.gpu.max_mem
        self.status["gpu_max_temp_c"] = self.gpu.max_temp
        tmp = self.status_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.status, indent=2), encoding="utf-8")
        os.replace(tmp, self.status_path)

    def time_left(self):
        return self.deadline - time.time()

    def task(self, name, cmd, timeout_s, json_out=None):
        """Run one tool as a subprocess; record result. Returns task record."""
        idx = len(self.status["tasks"]) + 1
        log = self.out / "logs" / f"{idx:03d}_{name}.log"
        rec = {"n": idx, "name": name, "cycle": self.status["cycle"], "start": now(), "log": str(log.relative_to(self.out))}
        self.status["current"] = rec
        self.save()
        t0 = time.time()
        timeout_s = max(60, min(timeout_s, self.time_left() + 600))
        try:
            with log.open("w", encoding="utf-8", errors="replace") as f:
                f.write(f"$ {' '.join(map(str, cmd))}\n\n")
                f.flush()
                p = subprocess.run(cmd, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT, timeout=timeout_s,
                                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
            rec["exit"] = p.returncode
        except subprocess.TimeoutExpired:
            rec["exit"] = "timeout"
        rec["seconds"] = round(time.time() - t0)
        rec["ok"] = rec["exit"] == 0
        if json_out and Path(json_out).exists():
            try:
                rec["result"] = json.loads(Path(json_out).read_text(encoding="utf-8"))
            except ValueError:
                pass
        tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]
        rec["tail"] = tail
        self.status["tasks"].append(rec)
        self.status.pop("current", None)
        self.save()
        write_report(self.out, self.status)
        print(f"[{now()}] {name}: {'OK' if rec['ok'] else 'FAILED (' + str(rec['exit']) + ')'} in {rec['seconds']}s")
        return rec


def write_report(out: Path, st: dict):
    """Human-readable rolling summary."""
    tasks = st["tasks"]
    lines = [f"# Overnight run {st['started']}", "",
             f"- Heartbeat: {st.get('heartbeat')}  |  phase: {st.get('phase')}  |  cycle: {st.get('cycle')}",
             f"- Deadline: {st.get('deadline')}",
             f"- Tasks: {len(tasks)} run, {sum(1 for t in tasks if not t['ok'])} failed",
             f"- GPU peak memory: {st.get('gpu_max_mem_mb')} MB, peak temperature: {st.get('gpu_max_temp_c')} C",
             f"- Engine args: {' '.join(st.get('engine_args') or []) or '(app defaults)'}", ""]
    env = st.get("environment", {})
    if env:
        lines += ["## Environment", "```"] + [f"{k}: {v}" for k, v in env.items()] + ["```", ""]
    lines += ["## Tasks", "", "| # | cycle | task | result | time | notes |", "|---|---|---|---|---|---|"]
    for t in tasks:
        note = ""
        r = t.get("result") or {}
        if t["name"].startswith("bench") and r:
            note = f"RTF {r.get('rtf_mean', 0):.3f}, peak GPU {r.get('peak_gpu_mb')} MB, WER {r.get('wer', 0) * 100:.1f}%"
        elif t["name"] == "eval" and r.get("summary"):
            parts = []
            for v, d in r["summary"].items():
                a = d.get("ALL", {})
                parts.append(f"{v}: WER {a.get('wer')}% / terms {a.get('term_recall')}%")
            note = "; ".join(parts)
        elif t["name"] in ("long", "churn", "gui") and r:
            fails = [f"{s}:{c}" for s, d in r.items() if isinstance(d, dict)
                     for c, v in d.get("checks", {}).items() if not v.get("ok")]
            m = (r.get("long") or {}).get("metrics", {})
            note = (f"RTF {m.get('rtf_mean')}, max queue {m.get('max_queue')}, final latency {m.get('final_latency_s')}s; "
                    if m else "") + ("FAILED: " + ", ".join(fails) if fails else "all checks passed")
        elif not t["ok"]:
            note = (t.get("tail") or [""])[-1][:120]
        lines.append(f"| {t['n']} | {t['cycle']} | {t['name']} | {'ok' if t['ok'] else 'FAIL ' + str(t['exit'])} "
                     f"| {t['seconds']}s | {note} |")
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def snapshot_environment(run: Run):
    env = {"python": sys.version.split()[0], "platform": sys.platform}
    try:
        import ctranslate2
        sys.path.insert(0, str(ROOT / "src"))
        import fw_engine
        fw_engine.register_cuda_dll_dirs()
        env["ctranslate2"] = ctranslate2.__version__
        env["cuda_devices"] = ctranslate2.get_cuda_device_count()
        if env["cuda_devices"]:
            env["cuda_compute_types"] = sorted(ctranslate2.get_supported_compute_types("cuda"))
    except Exception as exc:              # report, don't die: the point is to find out
        env["ctranslate2_error"] = repr(exc)
    if run.gpu.smi:
        q = subprocess.run([run.gpu.smi, "--query-gpu=name,driver_version,memory.total,compute_cap",
                            "--format=csv,noheader"], capture_output=True, text=True)
        env["gpu"] = q.stdout.strip() or q.stderr.strip()
    run.status["environment"] = env
    run.save()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    engine_args = []
    if "--" in argv:
        i = argv.index("--")
        argv, engine_args = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--long-minutes", type=float, default=30.0)
    ap.add_argument("--skip", default="", help="comma list of task names to skip (e.g. gui)")
    ap.add_argument("--testdict", type=Path, help="existing synthetic dictation folder (default: make one)")
    args = ap.parse_args(argv)

    out = args.out or ROOT / "results_overnight" / dt.datetime.now().strftime("%Y%m%d_%H%M")
    out.mkdir(parents=True, exist_ok=True)
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    deadline = time.time() + args.hours * 3600

    gpu = GpuSampler(out / "gpu.csv")
    gpu.start()
    keep_awake(True)
    run = Run(out, deadline, engine_args, gpu)
    print(f"Overnight run -> {out}  (deadline {run.status['deadline']})")
    try:
        snapshot_environment(run)
        S = ROOT / "scripts"
        td = args.testdict or out / "testdict"
        if not (td / "manifest.json").exists():
            backend = "sapi" if sys.platform == "win32" else "espeak"
            run.task("make_testdict", [PY, S / "make_test_dictation.py", "--out", td, "--backend", backend], 1800)
        manifest = td / "manifest.json"
        conf_wav = td / "fm_cardiac__conference.wav"
        clean_wav, clean_ref = td / "fm_diabetes_htn__clean.wav", td / "fm_diabetes_htn.txt"
        J = out / "json"

        while run.time_left() > 120:
            run.status["cycle"] += 1
            c = run.status["cycle"]
            first = not any(t["name"] == "smoke" for t in run.status["tasks"])
            if first and "smoke" not in skip:
                run.task("smoke", [PY, "-m", "pytest", "-q", "tests"], 900)
            if first and "bench" not in skip:
                for label, extra in (("bench_turbo", []), ("bench_turbo_beam1", ["--beam-size", "1"]),
                                     ("bench_large-v3", ["--model", "large-v3"]),
                                     ("bench_distil-v3.5", ["--model", "distil-large-v3.5"])):
                    if run.time_left() < 300:
                        break
                    if extra[:1] == ["--model"] and "--model" in engine_args:
                        continue                   # sandbox model override: skip model comparisons
                    j = J / f"{label}_c{c}.json"
                    run.task(label, [PY, S / "bench_engine.py", "--audio", clean_wav, "--reference", clean_ref,
                                     "--json", j] + extra + engine_args, 3600, j)
            plan = [
                ("eval", [S / "eval_dictation.py", "--manifest", manifest, "--show-missed"], 4 * 3600),
                ("long", [S / "stress_pipeline.py", "--audio", conf_wav, "--scenario", "long",
                          "--minutes", str(args.long_minutes)], int(args.long_minutes * 60 * 3) + 600),
                ("churn", [S / "stress_pipeline.py", "--audio", conf_wav, "--scenario", "cycles", "--cycles", "200",
                           "--scenario", "silence", "--scenario", "faults"], 3 * 3600),
                ("gui", [S / "stress_pipeline.py", "--audio", conf_wav, "--scenario", "gui", "--gui-cycles", "20"], 3600),
            ]
            for name, cmd, timeout_s in plan:
                if name in skip or run.time_left() < 120:
                    continue
                j = J / f"{name}_c{c}.json"
                run.task(name, [PY] + cmd + ["--json", j] + engine_args, timeout_s, j)
        run.status["phase"] = "finished"
    except KeyboardInterrupt:
        run.status["phase"] = "interrupted"
    except Exception as exc:
        run.status["phase"] = f"crashed: {exc!r}"
        raise
    finally:
        gpu.stop_evt.set()
        keep_awake(False)
        run.save()
        write_report(out, run.status)
        print(f"Done ({run.status['phase']}). Report: {out / 'REPORT.md'}")
    return 0 if all(t["ok"] for t in run.status["tasks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
