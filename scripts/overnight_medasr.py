"""Bounded, sequential local MedASR/Whisper matrix; no downloads or microphone.

--dry-run prints the finite plan without reading models, taking a lock, or
starting subprocesses. Results and logs stay in ignored results_medasr.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
from typing import Callable

import asr_trial_common as common


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLock:
    """OS-held exclusive lock; crashes release it, and its file is never unlinked."""

    def __init__(self, path: Path):
        self.path = path
        self.file = None

    def __enter__(self) -> RunLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.file.seek(0, os.SEEK_END) == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            raise RuntimeError("Another overnight runner holds the run lock") from exc
        return self

    def __exit__(self, *args: object) -> None:
        if self.file is not None:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
            self.file.close()
            self.file = None


@dataclass(frozen=True)
class Job:
    name: str
    dataset: str
    phase: str
    engine: str | None = None
    precision: str = "float32"
    realtime: bool = False
    repeats: int = 1
    dependencies: tuple[str, ...] = ()
    native_format: bool = False

    @property
    def gpu(self) -> bool:
        return self.engine is not None


def build_jobs(native_format: bool = False) -> list[Job]:
    """One finite pass, with each score immediately after its prerequisites."""
    jobs = [
        Job("whisper_real", "real", "real_offline", "whisper"),
        Job("medasr_real", "real", "real_offline", "medasr"),
        Job("paired_real_scores", "real", "real_scores",
            dependencies=("whisper_real", "medasr_real")),
        Job("medasr_real_float16", "real", "precision", "medasr", "float16"),
        Job("paired_precision_scores", "real", "precision_scores",
            dependencies=("medasr_real", "medasr_real_float16")),
        Job("whisper_real_paced3", "real", "latency", "whisper", realtime=True, repeats=3),
        Job("medasr_real_paced3", "real", "latency", "medasr", realtime=True, repeats=3),
        Job("paired_latency_scores", "real", "latency_scores",
            dependencies=("whisper_real_paced3", "medasr_real_paced3")),
        Job("whisper_snippets", "snippets", "synthetic_snippets", "whisper"),
        Job("medasr_snippets", "snippets", "synthetic_snippets", "medasr"),
        Job("paired_snippets_scores", "snippets", "synthetic_snippets_scores",
            dependencies=("whisper_snippets", "medasr_snippets")),
        Job("whisper_testdict", "testdict", "synthetic_testdict", "whisper"),
        Job("medasr_testdict", "testdict", "synthetic_testdict", "medasr"),
        Job("paired_testdict_scores", "testdict", "synthetic_testdict_scores",
            dependencies=("whisper_testdict", "medasr_testdict")),
        Job("medasr_real_stability5", "real", "stability", "medasr", repeats=5),
        Job("stability_scores", "real", "stability_scores",
            dependencies=("medasr_real_stability5",)),
    ]
    if native_format:
        # Float16 has already failed numerically here. This experiment changes
        # formatting only, with a fresh paired baseline under the new source.
        jobs = [replace(job, native_format=job.engine == "medasr") for job in jobs
                if job.phase not in ("precision", "precision_scores")]
    return jobs


@dataclass(frozen=True)
class Config:
    root: Path
    out: Path
    manifests: dict[str, Path]
    model_path: Path
    hours: float = 6.0
    task_timeout: float = 3600.0
    poll_seconds: float = 5.0
    thermal_seconds: float = 60.0
    gpu_monitor: bool = True
    native_format: bool = False

    def python(self, medasr: bool = False) -> Path:
        return self.root / ("venvmedasr" if medasr else "venv1060") / "Scripts" / "python.exe"


def command_for(job: Job, config: Config) -> list[str]:
    command = [str(config.python(job.engine == "medasr")),
               str(config.root / "scripts" / ("trial_asr.py" if job.gpu else "score_asr_trial.py")),
               "--manifest", str(config.manifests[job.dataset]),
               "--out", str(config.out / (job.name + ".json"))]
    if job.gpu:
        command += ["--engine", str(job.engine), "--precision", job.precision,
                    "--repeats", str(job.repeats)]
        if job.engine == "medasr":
            command += ["--model-path", str(config.model_path)]
            if job.native_format:
                command += ["--medasr-format", "native-v1"]
        if job.realtime:
            command.append("--realtime")
    else:
        for dependency in job.dependencies:
            command += ["--run", str(config.out / (dependency + ".json"))]
    return command


def fingerprints(config: Config, jobs: list[Job]) -> tuple[dict, dict[str, list[dict]]]:
    """Freeze references/audio, pipeline, runner, commands and environment inputs."""
    corpora, entries = {}, {}
    for dataset, count in (("real", 30), ("snippets", 60), ("testdict", 40)):
        entries[dataset], digest = common.load_corpus([config.manifests[dataset]])
        if len(entries[dataset]) != count:
            raise ValueError(f"{dataset} must contain {count} clips")
        corpora[dataset] = digest
    sources = common.source_hashes()
    sources["scripts/overnight_medasr.py"] = common.sha256(Path(__file__))
    environment = {}
    paths = [config.python(), config.python(True)]
    paths += [config.root / name / "pyvenv.cfg" for name in ("venv1060", "venvmedasr")]
    paths += list(config.root.glob("requirements*.txt"))
    for path in paths:
        environment[path.relative_to(config.root).as_posix()] = common.sha256(path)
    settings = dict(commands=[command_for(job, config) for job in jobs],
                    hours=config.hours, task_timeout=config.task_timeout,
                    poll_seconds=config.poll_seconds, thermal_seconds=config.thermal_seconds,
                    gpu_monitor=config.gpu_monitor, environment=environment)
    return dict(source=sources, corpus=corpora, config=common.canonical_hash(settings)), entries


def validate_output(job: Job, path: Path, frozen: dict, entries: list[dict],
                    model: dict) -> None:
    """Check completion/config/coverage without importing an inference runtime."""
    result = json.loads(path.read_text(encoding="utf-8"))
    trial_sources = {k: v for k, v in frozen["source"].items()
                     if k != "scripts/overnight_medasr.py"}
    if (result.get("schema") != 1 or result.get("corpus_sha256") != frozen["corpus"][job.dataset]
            or result.get("source_sha256") != trial_sources):
        raise ValueError("Output source/corpus provenance mismatch")
    if not job.gpu:
        if set(result.get("runs", {})) != set(job.dependencies):
            raise ValueError("Score output does not contain the paired runs")
        return
    if (result.get("completed") is not True or result.get("engine") != job.engine
            or result.get("repeats") != job.repeats
            or result.get("replay") != ("realtime" if job.realtime else "offline")
            or result.get("versions", {}).get("wordfreq") != "3.1.1"):
        raise ValueError("Incomplete trial or replay configuration mismatch")
    actual_config = result.get("config", {})
    if actual_config.get("device") != "cuda":
        raise ValueError("GPU trial did not use CUDA")
    if job.engine == "medasr":
        expected = dict(model=common.MODEL_ID, revision=common.MODEL_REVISION,
                        precision=job.precision, decoding="greedy CTC")
        if result.get("model_integrity") != model:
            raise ValueError("Model integrity provenance mismatch")
        if actual_config.get("format_mode", "none") != ("native-v1" if job.native_format else "none"):
            raise ValueError("Native-format configuration mismatch")
    else:
        expected = dict(model="large-v3", compute="int8_float32", beam=5, patience=2.0)
    if any(actual_config.get(k) != v for k, v in expected.items()):
        raise ValueError("Inference configuration mismatch")
    expected_clips = {(e["clip_id"], repeat): e["audio_sha256"]
                      for e in entries for repeat in range(job.repeats)}
    actual_clips = {}
    for item in result.get("utterances", []):
        key = (item["clip_id"], item["repeat"])
        if (key in actual_clips or key not in expected_clips
                or item.get("audio_sha256") != expected_clips[key]
                or any(not isinstance(item.get(k), str) for k in ("raw", "cleaned"))):
            raise ValueError("Invalid, duplicate or stale trial clip")
        actual_clips[key] = item["audio_sha256"]
    if actual_clips != expected_clips:
        raise ValueError("Missing clips; refusing incomplete output")


def kill_owned_tree(process: subprocess.Popen) -> None:
    """Target only our Popen PID/group; never kill by executable name."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        # venv launchers may own the actual Python worker as a descendant.
        result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=10, check=False)
        if result.returncode != 0 and process.poll() is None:
            raise RuntimeError("Could not terminate the owned child process tree")
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


class Executor:
    """One owned subprocess at a time; bounded waits keep status/health live."""

    def __init__(self, config: Config, deadline: float,
                 clock: Callable[[], float] = time.monotonic,
                 popen: Callable = subprocess.Popen,
                 killer: Callable = kill_owned_tree):
        self.config, self.deadline, self.clock = config, deadline, clock
        self.popen, self.killer = popen, killer
        self.active_limit: float | None = None

    def spawn(self, command: list[str], **kwargs: object) -> subprocess.Popen:
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        return self.popen(command, cwd=self.config.root, stdin=subprocess.DEVNULL, **kwargs)

    def run(self, command: list[str], log: Path, update: Callable[[int], None],
            monitor: Callable[[], None]) -> dict:
        started = self.clock()
        if started >= self.deadline:
            return dict(state="deadline", returncode=None, pid=None)
        limit = min(self.deadline, started + self.config.task_timeout)
        self.active_limit = limit
        process = None
        with log.open("w", encoding="utf-8") as stream:
            try:
                env = dict(os.environ, PYTHONUTF8="1", HF_HUB_OFFLINE="1",
                           TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
                process = self.spawn(command, stdout=stream, stderr=subprocess.STDOUT, env=env)
                update(process.pid)
                while True:
                    remaining = limit - self.clock()
                    if remaining <= 0:
                        self.killer(process)
                        state = "deadline" if self.clock() >= self.deadline else "timeout"
                        return dict(state=state, returncode=process.returncode, pid=process.pid)
                    try:
                        code = process.wait(timeout=min(self.config.poll_seconds, remaining))
                        if self.clock() >= limit:
                            state = "deadline" if self.clock() >= self.deadline else "timeout"
                        else:
                            state = "success" if code == 0 else "failed"
                        return dict(state=state, returncode=code, pid=process.pid)
                    except subprocess.TimeoutExpired:
                        update(process.pid)
                        if self.clock() < limit:
                            monitor()
            except BaseException:
                if process is not None and process.poll() is None:
                    self.killer(process)
                raise
            finally:
                self.active_limit = None

    def sample_gpu(self) -> list[dict] | None:
        """Optional telemetry also has a short timeout and owned-child cleanup."""
        executable = shutil.which("nvidia-smi")
        remaining = min(self.deadline, self.active_limit or self.deadline) - self.clock()
        if executable is None or remaining <= 0:
            return None
        process = self.spawn([executable, "--query-gpu=temperature.gpu,memory.used,memory.total",
                              "--format=csv,noheader,nounits"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        try:
            output, _ = process.communicate(timeout=min(3.0, remaining))
            if process.returncode != 0:
                return None
            return [dict(temperature_c=float(parts[0]), memory_used_mb=float(parts[1]),
                         memory_total_mb=float(parts[2]))
                    for line in output.splitlines() if line.strip()
                    for parts in [line.split(",")]]
        except (subprocess.TimeoutExpired, ValueError, IndexError):
            if process.poll() is None:
                self.killer(process)
            return None
        except BaseException:
            if process.poll() is None:
                self.killer(process)
            raise


class ThermalGuard:
    def __init__(self, sustained_seconds: float):
        self.sustained_seconds = sustained_seconds
        self.high_since: float | None = None
        self.stopped = False

    def observe(self, samples: list[dict] | None, now: float) -> bool:
        if samples and all(math.isfinite(s["temperature_c"]) for s in samples):
            if max(s["temperature_c"] for s in samples) > 85:
                if self.high_since is None:
                    self.high_since = now
                if now - self.high_since >= self.sustained_seconds:
                    self.stopped = True
            else:
                self.high_since = None
        else:
            self.high_since = None
        return self.stopped


class Runner:
    def __init__(self, config: Config, resume: bool = False,
                 clock: Callable[[], float] = time.monotonic,
                 executor_factory: Callable = Executor,
                 fingerprint_fn: Callable = fingerprints,
                 verifier: Callable = common.verify_model,
                 validator: Callable = validate_output,
                 wall_clock: Callable[[], float] = time.time):
        self.config, self.resume, self.clock = config, resume, clock
        self.jobs = build_jobs(config.native_format)
        self.executor_factory, self.fingerprint_fn = executor_factory, fingerprint_fn
        self.verifier, self.validator = verifier, validator
        self.wall_clock = wall_clock
        self.status: dict = {}
        self.model: dict = {}

    def save(self) -> None:
        self.status["heartbeat_utc"] = utc_now()
        common.write_json(self.config.out / "status.json", self.status)

    def run(self) -> int:
        # One global lock covers new runs and resumes in every result directory.
        with RunLock(self.config.root / "results_medasr" / ".overnight.lock"):
            return self._run_locked()

    def _run_locked(self) -> int:
        wall_started = self.wall_clock()
        started_utc = datetime.fromtimestamp(wall_started, timezone.utc).isoformat()
        deadline_utc = datetime.fromtimestamp(
            wall_started + self.config.hours * 3600, timezone.utc).isoformat()
        frozen, entries = self.fingerprint_fn(self.config, self.jobs)
        old = {}
        status_path = self.config.out / "status.json"
        if self.resume:
            old = json.loads(status_path.read_text(encoding="utf-8"))
            if old.get("schema") != 1 or old.get("fingerprints") != frozen:
                raise ValueError("Stale resume: source, corpus or configuration changed; use a fresh run")
            try:
                start = datetime.fromisoformat(old["started_utc"])
                end = datetime.fromisoformat(old["deadline_utc"])
                if (start.tzinfo is None or end.tzinfo is None
                        or start.utcoffset().total_seconds() != 0
                        or end.utcoffset().total_seconds() != 0
                        or abs((end - start).total_seconds() - self.config.hours * 3600) > .001):
                    raise ValueError("Invalid original run window")
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Malformed resume start/deadline; refusing to extend the run") from exc
            started_utc, deadline_utc = old["started_utc"], old["deadline_utc"]
        elif self.config.out.exists():
            raise ValueError("Output already exists; use --resume or a fresh output directory")
        self.config.out.mkdir(parents=True, exist_ok=True)
        (self.config.out / "logs").mkdir(exist_ok=True)
        end_wall = datetime.fromisoformat(deadline_utc).timestamp()
        deadline = self.clock() + max(0, end_wall - self.wall_clock())
        self.status = dict(schema=1, started_utc=started_utc, phase="preflight", current_job=None,
                           pid=None, fingerprints=frozen, tasks=dict(old.get("tasks", {})), resumed=self.resume,
                           hours=self.config.hours, thermal_stop=bool(old.get("thermal_stop")),
                           model_fingerprint=old.get("model_fingerprint"),
                           deadline_utc=deadline_utc,
                           dataset_note="30 fictional real-headset clips; synthetic snippets60 and "
                           "testdict40 scored separately; not 130 independent samples")
        self.save()
        if self.clock() >= deadline:
            self.status.update(phase="deadline", finished_utc=utc_now())
            self.save()
            return 1
        try:
            self.model = self.verifier(self.config.model_path)
        except (OSError, ValueError, KeyError, TypeError):
            self.status.update(phase="blocked_model_access", error=
                "Pinned local MedASR snapshot is absent or fails integrity verification. "
                "Finish authorized model access/download and verify integrity.json before resuming. "
                "No GPU job was started.")
            self.save()
            return 2
        self.status["model_fingerprint"] = common.canonical_hash(self.model)
        old_tasks = old.get("tasks", {})
        if any(r.get("state") == "success" for r in old_tasks.values()):
            if old.get("model_fingerprint") != self.status["model_fingerprint"]:
                raise ValueError("Stale resume: model fingerprint changed")
        # Validate every reusable artifact before launching even the first job.
        for job in self.jobs:
            record = old_tasks.get(job.name, {})
            if record.get("state") == "success":
                path = self.config.out / (job.name + ".json")
                try:
                    if record.get("returncode") != 0 or common.sha256(path) != record.get("output_sha256"):
                        raise ValueError("Successful task artifact changed or is missing")
                    if any(old_tasks.get(dep, {}).get("state") != "success" for dep in job.dependencies):
                        raise ValueError("Successful score has incomplete dependencies")
                    self.validator(job, path, frozen, entries[job.dataset], self.model)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"Stale resume artifact: {job.name}; rerun in a fresh directory") from exc
                self.status["tasks"][job.name] = dict(record, reused=True)
        executor = self.executor_factory(self.config, deadline, self.clock)
        thermal = ThermalGuard(self.config.thermal_seconds)
        # Once triggered, thermal blocking persists on resume for this run.
        thermal.stopped = bool(old.get("thermal_stop"))

        def monitor() -> None:
            if not self.config.gpu_monitor:
                return
            try:
                samples = executor.sample_gpu()
            except OSError:
                samples = None
            stopped = thermal.observe(samples, self.clock())
            self.status.update(thermal_stop=stopped, gpu=samples,
                               gpu_monitor="available" if samples else "unavailable")
            if stopped:
                self.status["thermal_reason"] = "Temperature sustained above 85 C; no new GPU jobs"
            with (self.config.out / "logs" / "gpu.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(dict(utc=utc_now(), samples=samples)) + "\n")
            self.save()

        try:
            for job in self.jobs:
                tasks = self.status["tasks"]
                if tasks.get(job.name, {}).get("state") == "success":
                    continue
                if self.clock() >= deadline:
                    self.status["phase"] = "deadline"
                    break
                if job.gpu:
                    monitor()
                if self.clock() >= deadline:
                    self.status["phase"] = "deadline"
                    break
                if any(tasks.get(dep, {}).get("state") != "success" for dep in job.dependencies):
                    tasks[job.name] = dict(state="skipped_dependency", returncode=None, pid=None)
                    self.save()
                    continue
                if job.gpu and thermal.stopped:
                    tasks[job.name] = dict(state="skipped_thermal", returncode=None, pid=None)
                    self.save()
                    continue
                self.status.update(phase=job.phase, current_job=job.name, pid=None)
                attempt = int(old_tasks.get(job.name, {}).get("attempt", 0)) + 1
                log = self.config.out / "logs" / f"{job.name}_{attempt}.log"
                tasks[job.name] = dict(state="running", returncode=None, attempt=attempt,
                                       log=str(log.relative_to(self.config.out)), started_utc=utc_now())
                self.save()

                def update(pid: int) -> None:
                    self.status["pid"] = pid
                    tasks[job.name]["pid"] = pid
                    self.save()

                try:
                    # A dependency hash is rechecked immediately before scoring.
                    for dep in job.dependencies:
                        if common.sha256(self.config.out / (dep + ".json")) != tasks[dep]["output_sha256"]:
                            raise ValueError("Dependency output changed before scoring")
                    result = executor.run(command_for(job, self.config), log, update, monitor)
                    tasks[job.name].update(result)
                    if result["state"] == "success":
                        path = self.config.out / (job.name + ".json")
                        self.validator(job, path, frozen, entries[job.dataset], self.model)
                        tasks[job.name]["output_sha256"] = common.sha256(path)
                except (OSError, ValueError, KeyError, TypeError):
                    tasks[job.name].update(state="failed", error=
                        "Task launch, output integrity or completeness check failed; inspect local task log")
                tasks[job.name]["finished_utc"] = utc_now()
                self.status.update(current_job=None, pid=None)
                self.save()
                if tasks[job.name]["state"] == "deadline" or self.clock() >= deadline:
                    self.status["phase"] = "deadline"
                    break
            else:
                self.status["phase"] = "stopped_thermal" if thermal.stopped else (
                    "complete" if all(r["state"] == "success" for r in self.status["tasks"].values())
                    else "completed_with_failures")
        except KeyboardInterrupt:
            self.status.update(phase="interrupted", current_job=None, pid=None)
        except Exception:
            self.status.update(phase="failed", current_job=None, pid=None,
                               error="Runner failed; owned child cleanup was attempted")
            self.save()
            raise
        self.status["finished_utc"] = utc_now()
        self.save()
        return 0 if self.status["phase"] == "complete" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hours", type=float, default=6.0)
    parser.add_argument("--task-timeout", type=float, default=3600.0, help="seconds per subprocess")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--thermal-seconds", type=float, default=60.0,
                        help="sustained temperature above 85 C stops new GPU jobs")
    parser.add_argument("--no-gpu-monitor", action="store_true")
    parser.add_argument("--native-format", action="store_true",
                        help="separate float32 native-marker matrix; excludes failed float16 precision")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--out", type=Path)
    group.add_argument("--resume", type=Path)
    parser.add_argument("--real-manifest", type=Path,
                        default=common.ROOT / "results_1060" / "real_headset" / "manifest.json")
    parser.add_argument("--snippets-manifest", type=Path,
                        default=common.ROOT / "results_1060" / "snippets" / "manifest.json")
    parser.add_argument("--testdict-manifest", type=Path,
                        default=common.ROOT / "results_1060" / "testdict" / "manifest.json")
    parser.add_argument("--model-path", type=Path,
                        default=common.ROOT / "models_medasr" / common.MODEL_REVISION)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    for name in ("hours", "task_timeout", "poll_seconds", "thermal_seconds"):
        if not math.isfinite(getattr(args, name)) or getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    out = (args.resume or args.out or common.ROOT / "results_medasr" / f"overnight_{stamp}").resolve()
    config = Config(common.ROOT, out,
                    dict(real=args.real_manifest.resolve(), snippets=args.snippets_manifest.resolve(),
                         testdict=args.testdict_manifest.resolve()), args.model_path.resolve(),
                    args.hours, args.task_timeout, args.poll_seconds, args.thermal_seconds,
                    not args.no_gpu_monitor, args.native_format)
    if args.dry_run:
        print("Finite sequential matrix; real30, snippets60 and testdict40 remain separate.")
        for job in build_jobs(config.native_format):
            print(f"{job.name}: dependencies={','.join(job.dependencies) or 'none'}")
            print(subprocess.list2cmdline(command_for(job, config)))
        return 0
    try:
        out.relative_to(common.ROOT / "results_medasr")
        if out == common.ROOT / "results_medasr":
            raise ValueError("Use a run subdirectory inside results_medasr")
        common.local_result_path(out)
        return Runner(config, resume=args.resume is not None).run()
    except (OSError, ValueError, RuntimeError):
        # Avoid echoing exceptions that might contain reference text or secrets.
        print("Runner could not start or safely continue. Check the local status and "
              "run lock; stale resume inputs require a fresh output directory.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
