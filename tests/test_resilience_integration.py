"""Opt-in real verifier termination and overlapping-run recovery exercises."""

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

from restoreproof.contract import APPROVED_IMAGE
from restoreproof.demo import create_demo
from restoreproof.docker_postgres import DockerPostgres
from restoreproof.engine import verify
from restoreproof.process import run_command

FIXTURE_LABEL = "io.restoreproof.resilience_fixture"


def _save(path, value):
    temporary = path.with_suffix(".writing")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _worker(contract, output, marker, release, phase):
    """Pause inside the real engine's phase, without adding production hooks."""
    class CheckpointTarget(DockerPostgres):
        paused = False

        def checkpoint(self, current):
            if self.paused or current != phase:
                return
            self.paused = True
            _save(marker, {"run_id": self.run_id, "container_id": self.container_id,
                           "phase": current, "pid": os.getpid()})
            deadline = time.monotonic() + 120
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("Test checkpoint was not released within 120 seconds.")
                time.sleep(0.05)

        def restore(self, archive, expected_sha256):
            super().restore(archive, expected_sha256)
            self.checkpoint("restore")

        def query(self, sql):
            if phase == "active-query" and not self.paused:
                self.paused = True
                tag = "restoreproof-resilience-" + self.run_id
                _save(marker, {"run_id": self.run_id, "container_id": self.container_id,
                               "phase": "checks", "pid": os.getpid(), "query_tag": tag})
                return super().query(f"SELECT to_json(true) FROM pg_sleep(60) /* {tag} */")
            result = super().query(sql)
            self.checkpoint("checks")
            return result

    report = verify(contract, output, backend_factory=CheckpointTarget)
    print(json.dumps({"run_id": report["run_id"], "status": report["status"],
                      "report_path": report["report_path"]}), flush=True)
    return report["exit_code"]


def _kill_worker_tree(process):
    """Only terminate the process tree/group created for this test worker."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        taskkill = str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe")
        result = subprocess.run([taskkill, "/PID", str(process.pid), "/T", "/F"],
                                capture_output=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and process.poll() is None:
            raise RuntimeError("Could not terminate the owned verifier process tree.")
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=15)


@unittest.skipUnless(os.environ.get("RESTOREPROOF_INTEGRATION") == "1",
                     "requires Docker; opt in explicitly")
class ResilienceIntegrationTests(unittest.TestCase):
    def setUp(self):
        evidence = os.environ.get("RESTOREPROOF_EVIDENCE_DIR")
        if evidence:
            scenario = ("active-query" if "active_query" in self._testMethodName else
                        "overlap" if "overlapping" in self._testMethodName else
                        "checks-kill" if "checks_phase" in self._testMethodName else "restore-kill")
            self.root = Path(evidence).resolve() / scenario / uuid.uuid4().hex
            self.root.mkdir(parents=True)
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        self.output = self.root / "runs"
        self.workers = []
        self.foreign_token = uuid.uuid4().hex
        self.foreign_name = "restoreproof-foreign-" + self.foreign_token
        self.foreign_attempted = False
        self.addCleanup(self._cleanup_resources)
        self.contract = create_demo(self.root / "fixtures", "healthy")

    def _docker(self, *args):
        return run_command(["docker", *args], timeout=20).decode("utf-8")

    def _inspect(self, container_id):
        return json.loads(self._docker("inspect", "--format", "{{json .}}", container_id))

    def _create_foreign_fixture(self):
        self.foreign_attempted = True
        raw = self._docker("create", "--name", self.foreign_name,
                           "--label", FIXTURE_LABEL + "=" + self.foreign_token,
                           "--network", "none", "--memory", "32m", "--cpus", "0.25",
                           "--pids-limit", "16", "--read-only",
                           "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=16777216",
                           "--entrypoint", "/bin/sleep", APPROVED_IMAGE, "360").strip()
        self.assertRegex(raw, r"^[a-f0-9]{64}$")
        self._docker("start", raw)
        return raw

    def _launch(self, phase):
        number = len(self.workers)
        marker = self.root / f"worker-{number}.json"
        release = self.root / f"release-{number}"
        log_path = self.root / f"worker-{number}.log"
        log = log_path.open("wb")
        environment = os.environ.copy()
        source = str(Path(__file__).resolve().parents[1] / "src")
        environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
        options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                   if os.name == "nt" else {"start_new_session": True})
        try:
            child = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--resilience-worker",
                 str(self.contract), str(self.output), str(marker), str(release), phase],
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, env=environment, **options)
        except BaseException:
            log.close()
            raise
        worker = {"child": child, "marker": marker, "release": release,
                  "log": log, "log_path": log_path}
        self.workers.append(worker)
        return worker

    def _checkpoint(self, worker, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if worker["marker"].exists():
                return json.loads(worker["marker"].read_text(encoding="utf-8"))
            if worker["child"].poll() is not None:
                self.fail("Verifier exited before checkpoint: " +
                          worker["log_path"].read_text(encoding="utf-8")[-4000:])
            time.sleep(0.05)
        self.fail(f"Verifier did not reach checkpoint within {timeout} seconds: {worker['log_path']}")

    def _wait_active_query(self, worker, checkpoint):
        """Require observed server execution, not just the child's marker."""
        tag = checkpoint["query_tag"]
        self.assertRegex(tag, r"^restoreproof-resilience-[a-f0-9]{32}$")
        sql = ("SELECT coalesce(json_agg(json_build_object('pid', pid, 'state', state, "
               "'wait_event_type', wait_event_type, 'wait_event', wait_event)), '[]'::json) "
               "FROM pg_stat_activity WHERE pid <> pg_backend_pid() AND state = 'active' "
               "AND wait_event_type = 'Timeout' AND wait_event = 'PgSleep' "
               f"AND position('{tag}' in query) > 0")
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            self.assertIsNone(worker["child"].poll(), "Verifier exited before in-flight query observation")
            raw = run_command(["docker", "exec", checkpoint["container_id"], "psql", "-XqAt",
                               "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", "restoreproof", "-c", sql],
                              timeout=max(0.01, min(3, deadline - time.monotonic())))
            observed = json.loads(raw)
            if observed:
                self.assertEqual(len(observed), 1, observed)
                return observed[0]
            time.sleep(0.1)
        self.fail("The tagged verifier query did not reach pg_stat_activity PgSleep within 12 seconds")

    def _journal(self, checkpoint):
        return self.output / checkpoint["run_id"] / "report.json"

    def _finish(self, worker, checkpoint):
        worker["release"].touch()
        code = worker["child"].wait(timeout=90)
        report = json.loads(self._journal(checkpoint).read_text(encoding="utf-8"))
        self.assertEqual(code, 0, {"report": report, "log": str(worker["log_path"])})
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["cleanup"]["status"], "PASS", report)
        self.assertEqual(report["cleanup"]["remaining"], [], report)
        return report

    def _interrupt(self, phase):
        started = time.monotonic()
        foreign_id = self._create_foreign_fixture()
        worker = self._launch(phase)
        checkpoint = self._checkpoint(worker, timeout=45 if phase == "active-query" else 90)
        active_query = self._wait_active_query(worker, checkpoint) if phase == "active-query" else None
        journal_path = self._journal(checkpoint)
        before = journal_path.read_bytes()
        journal = json.loads(before)
        self.assertEqual(journal["phase"], "checks" if active_query else phase, journal)
        self.assertEqual(journal["status"], "INCOMPLETE", journal)
        self.assertEqual(journal["exit_code"], 2)
        self.assertTrue(self._inspect(checkpoint["container_id"])["State"]["Running"])
        _kill_worker_tree(worker["child"])
        killed_after = time.monotonic() - started
        self.assertNotEqual(worker["child"].returncode, 0)
        self.assertEqual(journal_path.read_bytes(), before, "Hard kill unexpectedly finalized the journal")
        self.assertTrue(self._inspect(checkpoint["container_id"])["State"]["Running"])
        recovered = DockerPostgres.cleanup_run(APPROVED_IMAGE, journal["run_id"])
        repeated = DockerPostgres.cleanup_run(APPROVED_IMAGE, journal["run_id"])
        self.assertEqual(recovered["status"], "PASS", recovered)
        self.assertEqual(recovered["remaining"], [], recovered)
        self.assertEqual(repeated["status"], "PASS", repeated)
        self.assertEqual(repeated["remaining"], [], repeated)
        foreign = self._inspect(foreign_id)
        self.assertTrue(foreign["State"]["Running"], "Recovery stopped the unrelated fixture")
        self.assertEqual(foreign["Config"]["Labels"][FIXTURE_LABEL], self.foreign_token)
        self.assertEqual(journal_path.read_bytes(), before, "Cleanup must not turn an interrupted run into PASS")
        if active_query:
            self.assertLess(killed_after, 60, "The test must kill the worker before its full sleep can finish")
            self.assertLess(time.monotonic() - started, 120, "Active-query drill exceeded its wall-time budget")
        _save(self.root / "interruption.json", {"checkpoint": checkpoint,
              "child_returncode": worker["child"].returncode, "journal_status": journal["status"],
              "recovered": recovered, "repeated": repeated,
              "unrelated_container_id": foreign_id, "unrelated_container_retained": True,
              "active_query_observation": active_query, "kill_elapsed_seconds": round(killed_after, 3),
              "boundary": ("Hard kill while tagged SQL query was observed in PgSleep."
                           if active_query else "Hard kill at test-only pause after real operation, before phase returns.")})

    def test_hard_kill_during_restore_phase_recovers_only_owned_target(self):
        self._interrupt("restore")

    def test_hard_kill_during_checks_phase_preserves_incomplete_journal(self):
        self._interrupt("checks")

    def test_hard_kill_during_active_query_recovers_only_owned_target(self):
        self._interrupt("active-query")

    def test_overlapping_verifiers_share_output_without_cross_cleanup(self):
        first, second = self._launch("restore"), self._launch("restore")
        left, right = self._checkpoint(first), self._checkpoint(second)
        self.assertNotEqual(left["run_id"], right["run_id"])
        self.assertNotEqual(left["container_id"], right["container_id"])
        second_before = self._journal(right).read_bytes()
        for checkpoint in [left, right]:
            self.assertTrue(self._inspect(checkpoint["container_id"])["State"]["Running"])
        first_report = self._finish(first, left)
        self.assertIsNone(second["child"].poll(), "First cleanup terminated the second verifier")
        self.assertTrue(self._inspect(right["container_id"])["State"]["Running"])
        self.assertEqual(self._journal(right).read_bytes(), second_before)
        second_report = self._finish(second, right)
        self.assertEqual(json.loads(self._journal(left).read_text(encoding="utf-8")), first_report)
        _save(self.root / "concurrency.json", {
            "run_ids": [left["run_id"], right["run_id"]],
            "container_ids": [left["container_id"], right["container_id"]],
            "both_targets_live_before_release": True, "second_survived_first_cleanup": True,
            "statuses": [first_report["status"], second_report["status"]],
            "cleanup": [first_report["cleanup"], second_report["cleanup"]]})

    def _cleanup_resources(self):
        errors = []
        for worker in self.workers:
            try:
                _kill_worker_tree(worker["child"])
            except Exception as error:
                errors.append(f"Worker cleanup: {type(error).__name__}: {error}")
            finally:
                worker["log"].close()
        for path in self.output.glob("*/report.json"):
            try:
                run_id = json.loads(path.read_text(encoding="utf-8"))["run_id"]
                if not re.fullmatch(r"[a-f0-9]{32}", run_id) or path.parent.name != run_id:
                    raise ValueError("Unexpected run ownership in test journal")
                outcome = DockerPostgres.cleanup_run(APPROVED_IMAGE, run_id)
                if outcome["status"] != "PASS":
                    raise RuntimeError(str(outcome))
            except Exception as error:
                errors.append(f"Target cleanup: {type(error).__name__}: {error}")
        try:
            candidates = self._docker("ps", "-a", "--no-trunc", "--filter",
                                      "label=" + FIXTURE_LABEL + "=" + self.foreign_token,
                                      "--format", "{{.ID}}").split() if self.foreign_attempted else []
            for identifier in candidates:
                inspected = self._inspect(identifier)
                if (inspected["Id"] != identifier or inspected["Name"] != "/" + self.foreign_name
                        or inspected["Config"]["Labels"].get(FIXTURE_LABEL) != self.foreign_token):
                    raise RuntimeError("Refusing removal: foreign fixture ownership mismatch")
                self._docker("rm", "--force", identifier)
                remaining = self._docker("ps", "-a", "--no-trunc", "--filter", "id=" + identifier,
                                         "--format", "{{.ID}}").strip()
                if remaining:
                    raise RuntimeError("Owned foreign fixture remains after removal")
        except Exception as error:
            errors.append(f"Foreign fixture cleanup: {type(error).__name__}: {error}")
        _save(self.root / "test-cleanup.json", {"status": "INCOMPLETE" if errors else "PASS", "errors": errors})
        self.assertFalse(errors, "\n".join(errors))


if __name__ == "__main__":
    if len(sys.argv) == 7 and sys.argv[1] == "--resilience-worker":
        raise SystemExit(_worker(*(Path(value) for value in sys.argv[2:6]), sys.argv[6]))
    unittest.main()
