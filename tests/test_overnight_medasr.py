"""Offline orchestration checks: fake jobs, clocks and owned processes only."""
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import overnight_medasr as overnight


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeExecutor:
    def __init__(self, config, deadline, clock):
        self.config, self.deadline, self.clock = config, deadline, clock
        self.calls = []
        self.failures = set()
        self.temperatures = []

    def run(self, command, log, update, monitor):
        name = Path(command[command.index("--out") + 1]).stem
        self.calls.append(name)
        update(1234)
        log.write_text("timings only\n", encoding="utf-8")
        if name in self.failures:
            return dict(state="failed", returncode=1, pid=1234)
        (self.config.out / (name + ".json")).write_text("{}", encoding="utf-8")
        return dict(state="success", returncode=0, pid=1234)

    def sample_gpu(self):
        return self.temperatures.pop(0) if self.temperatures else None


def setup_runner(tmp_path, *, resume=False, frozen=None, verifier=None):
    config = overnight.Config(tmp_path, tmp_path / "results_medasr" / "overnight_test",
                              {k: tmp_path / (k + ".json") for k in ("real", "snippets", "testdict")},
                              tmp_path / "model", gpu_monitor=False)
    clock = Clock()
    executors = []

    def factory(config, deadline, clock):
        executor = FakeExecutor(config, deadline, clock)
        executors.append(executor)
        return executor

    runner = overnight.Runner(config, resume, clock, factory,
        lambda c, j: (frozen or dict(source={"x": "abc"}, corpus={}, config="fixed"),
                      {k: [] for k in c.manifests}),
        verifier or (lambda path: {"sha256": {"model": "abc"}}),
        lambda *args: None)
    return runner, executors


def test_finite_matrix_sequential_and_correct_environments(tmp_path):
    runner, executors = setup_runner(tmp_path)
    assert runner.run() == 0
    jobs = overnight.build_jobs()
    assert executors[0].calls == [j.name for j in jobs]
    assert len(jobs) == 16
    assert runner.status["phase"] == "complete"
    assert runner.status["pid"] is None
    assert runner.status["current_job"] is None
    assert runner.status["heartbeat_utc"].endswith("+00:00")
    for job in jobs:
        command = overnight.command_for(job, runner.config)
        assert command[0] == str(runner.config.python(job.engine == "medasr"))
        assert command.count("--manifest") == 1
        assert command[command.index("--manifest") + 1] == str(runner.config.manifests[job.dataset])
        if job.gpu:
            assert command[command.index("--repeats") + 1] == str(job.repeats)
            assert ("--realtime" in command) == job.realtime
        else:
            assert command.count("--run") == len(job.dependencies)
    assert jobs[3].precision == "float16"
    assert jobs[-2].repeats == 5
    assert jobs[-1].dependencies == ("medasr_real_stability5",)


def test_failed_job_skips_only_dependent_scores_and_finishes(tmp_path):
    runner, executors = setup_runner(tmp_path)
    original = runner.executor_factory

    def factory(*args):
        executor = original(*args)
        executor.failures.add("medasr_real")
        return executor

    runner.executor_factory = factory
    assert runner.run() == 1
    assert runner.status["tasks"]["paired_real_scores"]["state"] == "skipped_dependency"
    assert runner.status["tasks"]["paired_precision_scores"]["state"] == "skipped_dependency"
    assert "paired_latency_scores" in executors[0].calls
    assert "paired_snippets_scores" in executors[0].calls
    assert executors[0].calls[-1] == "stability_scores"
    assert runner.status["phase"] == "completed_with_failures"


def test_blocked_model_starts_no_jobs_and_can_resume(tmp_path):
    def absent(path):
        raise FileNotFoundError("secret must never be copied to status")

    runner, executors = setup_runner(tmp_path, verifier=absent)
    assert runner.run() == 2
    assert runner.status["phase"] == "blocked_model_access"
    assert "secret" not in json.dumps(runner.status)
    assert not executors
    retry, executors = setup_runner(tmp_path, resume=True)
    assert retry.run() == 0
    assert len(executors[0].calls) == 16


@pytest.mark.parametrize("component", ["source", "corpus", "config"])
def test_stale_resume_fingerprints_rejected_before_spawning(tmp_path, component):
    runner, _ = setup_runner(tmp_path)
    runner.run()
    changed = dict(runner.status["fingerprints"])
    changed[component] = "changed"
    retry, executors = setup_runner(tmp_path, resume=True, frozen=changed)
    with pytest.raises(ValueError, match="Stale resume"):
        retry.run()
    assert not executors


def test_resume_reuses_only_verified_successes_and_retries_failure(tmp_path):
    runner, _ = setup_runner(tmp_path)
    runner.run()
    status = runner.status
    status["tasks"]["medasr_real_stability5"].update(state="failed", returncode=1)
    status["tasks"]["stability_scores"].update(state="skipped_dependency", returncode=None)
    overnight.common.write_json(runner.config.out / "status.json", status)
    retry, executors = setup_runner(tmp_path, resume=True)
    assert retry.run() == 0
    assert executors[0].calls == ["medasr_real_stability5", "stability_scores"]
    assert retry.status["tasks"]["whisper_real"]["reused"] is True
    assert retry.status["tasks"]["medasr_real_stability5"]["attempt"] == 2
    assert (runner.config.out / "logs" / "medasr_real_stability5_1.log").exists()
    assert (runner.config.out / "logs" / "medasr_real_stability5_2.log").exists()


def test_resume_preserves_original_window_and_expired_resume_launches_no_jobs(tmp_path):
    runner, _ = setup_runner(tmp_path)
    runner.wall_clock = lambda: 1000000.0
    assert runner.run() == 0
    original_start = runner.status["started_utc"]
    original_deadline = runner.status["deadline_utc"]
    retry, executors = setup_runner(tmp_path, resume=True)
    retry.wall_clock = lambda: 1000000.0 + 6 * 3600 + 1
    retry.verifier = lambda p: pytest.fail("expired resume touched the model")
    assert retry.run() == 1
    assert not executors
    assert retry.status["phase"] == "deadline"
    assert retry.status["started_utc"] == original_start
    assert retry.status["deadline_utc"] == original_deadline


def test_resume_remaining_budget_includes_blocked_time(tmp_path):
    runner, _ = setup_runner(tmp_path)
    runner.wall_clock = lambda: 1000000.0
    runner.verifier = lambda p: (_ for _ in ()).throw(FileNotFoundError())
    assert runner.run() == 2
    retry, executors = setup_runner(tmp_path, resume=True)
    retry.wall_clock = lambda: 1000000.0 + 5 * 3600
    assert retry.run() == 0
    assert executors[0].deadline == 3600
    assert retry.status["deadline_utc"] == runner.status["deadline_utc"]


@pytest.mark.parametrize("deadline", [None, "invalid", "2030-01-01T00:00:00", "2030-01-01T00:00:00+00:00"])
def test_resume_malformed_or_extended_deadline_rejected(tmp_path, deadline):
    runner, _ = setup_runner(tmp_path)
    runner.run()
    runner.status["deadline_utc"] = deadline
    overnight.common.write_json(runner.config.out / "status.json", runner.status)
    retry, executors = setup_runner(tmp_path, resume=True)
    with pytest.raises(ValueError, match="Malformed resume"):
        retry.run()
    assert not executors


def test_resume_tampered_success_output_rejected(tmp_path):
    runner, _ = setup_runner(tmp_path)
    runner.run()
    (runner.config.out / "whisper_real.json").write_text("changed", encoding="utf-8")
    retry, executors = setup_runner(tmp_path, resume=True)
    with pytest.raises(ValueError, match="Stale resume artifact"):
        retry.run()
    assert not executors


def test_model_change_rejects_resume(tmp_path):
    runner, _ = setup_runner(tmp_path)
    runner.run()
    retry, executors = setup_runner(tmp_path, resume=True, verifier=lambda p: {"changed": True})
    with pytest.raises(ValueError, match="model fingerprint"):
        retry.run()
    assert not executors


def test_exclusive_lock_rejects_duplicate_and_releases(tmp_path):
    path = tmp_path / "run.lock"
    with overnight.RunLock(path):
        with pytest.raises(RuntimeError, match="run lock"):
            with overnight.RunLock(path):
                pytest.fail("duplicate lock acquired")
    with overnight.RunLock(path):
        assert path.exists()


class FakeProcess:
    def __init__(self, clock):
        self.clock, self.pid, self.returncode = clock, 4321, None

    def poll(self):
        return self.returncode

    def wait(self, timeout):
        self.clock.now += timeout
        raise subprocess.TimeoutExpired("fake", timeout)


@pytest.mark.parametrize("deadline,timeout,state", [(6, 100, "deadline"), (100, 6, "timeout")])
def test_owned_child_timeout_and_deadline(tmp_path, deadline, timeout, state):
    runner, _ = setup_runner(tmp_path)
    config = overnight.Config(**{**runner.config.__dict__, "task_timeout": timeout, "poll_seconds": 2})
    clock = Clock()
    process = FakeProcess(clock)
    killed, spawned, heartbeats = [], [], []

    def popen(command, **kwargs):
        spawned.append(kwargs)
        return process

    def killer(child):
        assert child is process
        killed.append(child.pid)
        child.returncode = -9

    executor = overnight.Executor(config, deadline, clock, popen, killer)
    result = executor.run(["fake"], tmp_path / "job.log", heartbeats.append, lambda: None)
    assert result["state"] == state
    assert killed == [4321]
    assert clock.now == 6
    assert len(heartbeats) >= 2
    if overnight.os.name == "nt":
        assert spawned[0]["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert spawned[0]["start_new_session"] is True


def test_expired_deadline_never_spawns(tmp_path):
    runner, _ = setup_runner(tmp_path)
    clock = Clock()
    clock.now = 10
    executor = overnight.Executor(runner.config, 10, clock,
        lambda *a, **kw: pytest.fail("spawn after deadline"))
    assert executor.run(["fake"], tmp_path / "log", lambda p: None, lambda: None)["state"] == "deadline"


@pytest.mark.skipif(overnight.os.name != "nt", reason="Windows owned-tree command")
def test_windows_kill_targets_exact_owned_pid_tree(monkeypatch):
    process = FakeProcess(Clock())
    commands = []

    def taskkill(command, **kwargs):
        commands.append(command)
        assert kwargs["timeout"] == 10
        process.returncode = -9
        return subprocess.CompletedProcess(command, 0)

    process.wait = lambda timeout: process.returncode
    monkeypatch.setattr(overnight.subprocess, "run", taskkill)
    overnight.kill_owned_tree(process)
    assert commands == [["taskkill", "/PID", "4321", "/T", "/F"]]


def test_wait_exception_cleans_up_owned_child(tmp_path):
    runner, _ = setup_runner(tmp_path)
    process = FakeProcess(Clock())
    killed = []

    def interrupt(timeout):
        raise KeyboardInterrupt()

    process.wait = interrupt
    executor = overnight.Executor(runner.config, 100, process.clock,
                                  lambda *a, **k: process, lambda p: killed.append(p.pid))
    with pytest.raises(KeyboardInterrupt):
        executor.run(["fake"], tmp_path / "log", lambda p: None, lambda: None)
    assert killed == [4321]


def test_runner_stops_matrix_after_deadline(tmp_path):
    runner, executors = setup_runner(tmp_path)
    original = runner.executor_factory

    def factory(*args):
        executor = original(*args)

        def run(command, log, update, monitor):
            executor.calls.append(Path(command[command.index("--out") + 1]).stem)
            runner.clock.now = executor.deadline
            return dict(state="deadline", returncode=-9, pid=1234)

        executor.run = run
        return executor

    runner.executor_factory = factory
    assert runner.run() == 1
    assert executors[0].calls == ["whisper_real"]
    assert runner.status["phase"] == "deadline"


def test_sustained_heat_is_latched_and_low_or_missing_resets():
    guard = overnight.ThermalGuard(60)
    high, low = [{"temperature_c": 86}], [{"temperature_c": 85}]
    assert not guard.observe(high, 0)
    assert not guard.observe(low, 59)
    assert not guard.observe(high, 60)
    assert not guard.observe(None, 119)
    assert not guard.observe(high, 120)
    assert not guard.observe(high, 179)
    assert guard.observe(high, 180)
    assert guard.observe(low, 181)


def test_thermal_stop_allows_completed_scores_but_no_new_gpu_jobs(tmp_path):
    runner, executors = setup_runner(tmp_path)
    runner.config = overnight.Config(**{**runner.config.__dict__, "gpu_monitor": True})
    original = runner.executor_factory

    def factory(*args):
        executor = original(*args)

        def sample():
            # First two real trials finish before heat is sustained.
            runner.clock.now += 30
            return [{"temperature_c": 86}]

        executor.sample_gpu = sample
        return executor

    runner.executor_factory = factory
    assert runner.run() == 1
    assert executors[0].calls == ["whisper_real", "medasr_real", "paired_real_scores"]
    assert runner.status["phase"] == "stopped_thermal"
    assert runner.status["thermal_stop"] is True


def test_dry_run_no_files_models_or_subprocesses(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(overnight.common, "ROOT", tmp_path)
    monkeypatch.setattr(overnight, "Runner", lambda *a, **k: pytest.fail("runner touched"))
    monkeypatch.setattr(overnight.common, "verify_model", lambda *a: pytest.fail("model touched"))
    monkeypatch.setattr(overnight.subprocess, "Popen", lambda *a, **k: pytest.fail("spawned"))
    assert overnight.main(["--dry-run", "--hours", "6"]) == 0
    assert "medasr_real_stability5" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_output_validation_refuses_partial_or_wrong_configuration(tmp_path):
    job = overnight.build_jobs()[1]
    frozen = dict(source={"scripts/overnight_medasr.py": "runner", "trial": "hash"}, corpus={"real": "corpus"})
    entries = [dict(clip_id="clip", audio_sha256="audio")]
    model = {"sha256": "model"}
    output = dict(schema=1, completed=True, engine="medasr", repeats=1, replay="offline",
                  corpus_sha256="corpus", source_sha256={"trial": "hash"},
                  versions={"wordfreq": "3.1.1"}, model_integrity=model,
                  config=dict(model=overnight.common.MODEL_ID, revision=overnight.common.MODEL_REVISION,
                              precision="float32", decoding="greedy CTC", device="cuda"),
                  utterances=[dict(clip_id="clip", repeat=0, audio_sha256="audio", raw="", cleaned="")])
    path = tmp_path / "output.json"
    overnight.common.write_json(path, output)
    overnight.validate_output(job, path, frozen, entries, model)
    output["utterances"] = []
    overnight.common.write_json(path, output)
    with pytest.raises(ValueError, match="Missing clips"):
        overnight.validate_output(job, path, frozen, entries, model)
    output["config"]["precision"] = "float16"
    overnight.common.write_json(path, output)
    with pytest.raises(ValueError, match="configuration"):
        overnight.validate_output(job, path, frozen, entries, model)


@pytest.mark.parametrize("flag", ["--hours", "--task-timeout", "--poll-seconds", "--thermal-seconds"])
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf"])
def test_reject_unbounded_or_invalid_limits(flag, value):
    with pytest.raises(SystemExit):
        overnight.main(["--dry-run", flag, value])
