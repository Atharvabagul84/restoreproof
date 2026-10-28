"""Hard-kill the public verifier CLI during observed pg_restore COPY writes."""

import json
import importlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

from restoreproof.contract import APPROVED_IMAGE
from restoreproof.docker_postgres import DockerPostgres
from restoreproof.process import run_command
from restore_write_fixture import ROW_COUNT, build_fixture
from test_resilience_integration import _kill_worker_tree, _save

FOREIGN_LABEL = "io.restoreproof.restore_write_fixture"
COPY_PROGRESS_SQL = """SELECT coalesce(json_agg(json_build_object(
    'pid', p.pid, 'command', p.command, 'type', p.type,
    'tuples_processed', p.tuples_processed, 'bytes_processed', p.bytes_processed,
    'state', a.state, 'query', a.query, 'wait_event', a.wait_event,
    'application_name', a.application_name)), '[]'::json)
    FROM pg_stat_progress_copy p JOIN pg_stat_activity a USING (pid)
    WHERE p.command = 'COPY FROM' AND p.type = 'PIPE'
      AND p.tuples_processed > 0 AND a.state = 'active'
      AND position('COPY drill.restore_rows ' in a.query) > 0"""


class CleanupControlBarrierTests(unittest.TestCase):
    """Actual files prove cleanup cannot outrun the control-response handshake."""

    def setUp(self):
        try:
            self.barrier = importlib.import_module("restore_write_worker").cleanup_after_release
        except (ImportError, AttributeError):
            self.fail("Cleanup/control response barrier is not implemented")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "owned-target"
        self.target.write_text("exists")
        self.marker, self.release = self.root / "waiting.json", self.root / "release.json"
        self.identity = {"run_id": "a" * 32, "container_id": "b" * 64, "worker_pid": os.getpid()}

    def cleanup(self):
        self.target.unlink()
        return {"status": "PASS", "remaining": []}

    def test_cleanup_waits_until_control_response_is_acknowledged(self):
        result, errors = [], []
        def run():
            try:
                result.append(self.barrier(self.cleanup, self.marker, self.release,
                                           self.identity, timeout_seconds=2))
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=run)
        worker.start()
        try:
            deadline = time.monotonic() + 1
            while not self.marker.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            self.assertTrue(self.marker.exists(), "Worker must expose its waiting cleanup boundary")
            self.assertTrue(self.target.exists(), "Cleanup ran before the control response")
            self.assertTrue(worker.is_alive())
            observed = json.loads(self.marker.read_text())
            self.assertEqual(observed["identity"], self.identity)
            self.assertEqual(observed["state"], "waiting-for-control-response")
        finally:
            _save(self.release, self.identity)
            worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result, [{"status": "PASS", "remaining": []}])
        self.assertFalse(self.target.exists())

    def test_missing_control_response_times_out_but_still_cleans(self):
        with self.assertRaises(TimeoutError):
            self.barrier(self.cleanup, self.marker, self.release, self.identity, timeout_seconds=0.05)
        self.assertFalse(self.target.exists(), "A failed handshake must not leak its owned target")

    def test_wrong_run_release_cannot_masquerade_as_confirmed_control_response(self):
        _save(self.release, {**self.identity, "run_id": "c" * 32})
        with self.assertRaises(ValueError):
            self.barrier(self.cleanup, self.marker, self.release, self.identity, timeout_seconds=0.1)
        self.assertFalse(self.target.exists())


@unittest.skipUnless(os.environ.get("RESTOREPROOF_INTEGRATION") == "1",
                     "requires Docker; opt in explicitly")
class RestoreWriteIntegrationTests(unittest.TestCase):
    def setUp(self):
        evidence = os.environ.get("RESTOREPROOF_EVIDENCE_DIR")
        if evidence:
            self.root = Path(evidence).resolve() / "restore-write" / uuid.uuid4().hex
            self.root.mkdir(parents=True)
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        self.workers = []
        self.output = self.root / "runs"
        self.foreign_token = uuid.uuid4().hex
        self.foreign_name = "restoreproof-write-foreign-" + self.foreign_token
        self.foreign_attempted = False
        self.addCleanup(self._cleanup_resources)
        self.contract, self.lock_key = build_fixture(self.root / "fixture")

    def _docker(self, *args, timeout=10):
        return run_command(["docker", *args], timeout=timeout).decode("utf-8")

    def _inspect(self, identifier):
        return json.loads(self._docker("inspect", "--format", "{{json .}}", identifier))

    def _sql(self, identifier, sql, timeout=3):
        return self._docker("exec", identifier, "psql", "-XqAt", "-v", "ON_ERROR_STOP=1",
                            "-U", "postgres", "-d", "restoreproof", "-c", sql, timeout=timeout)

    def _foreign_fixture(self):
        self.foreign_attempted = True
        identifier = self._docker("create", "--name", self.foreign_name,
                                  "--label", FOREIGN_LABEL + "=" + self.foreign_token,
                                  "--network", "none", "--read-only", "--memory", "32m",
                                  "--cpus", "0.25", "--pids-limit", "16", "--tmpfs",
                                  "/var/lib/postgresql/data:rw,noexec,nosuid,size=16777216",
                                  "--entrypoint", "/bin/sleep", APPROVED_IMAGE, "180").strip()
        self.assertRegex(identifier, r"^[a-f0-9]{64}$")
        self._docker("start", identifier)
        return identifier

    def _launch(self, name, *, defer_cleanup=False):
        output = self.output / name
        log_path = self.root / (name + ".log")
        log = log_path.open("wb")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src") + os.pathsep + environment.get("PYTHONPATH", "")
        options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}
                   if os.name == "nt" else {"start_new_session": True})
        cleanup_marker = self.root / (name + "-cleanup-waiting.json")
        cleanup_release = self.root / (name + "-cleanup-release.json")
        command = [sys.executable, "-m", "restoreproof", "verify", str(self.contract), "--output", str(output)]
        if defer_cleanup:
            command = [sys.executable, str(Path(__file__).with_name("restore_write_worker.py").resolve()),
                       str(self.contract), str(output), str(cleanup_marker), str(cleanup_release)]
        try:
            child = subprocess.Popen(command,
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                     env=environment, **options)
        except BaseException:
            log.close()
            raise
        worker = {"child": child, "log": log, "log_path": log_path, "output": output,
                  "cleanup_marker": cleanup_marker, "cleanup_release": cleanup_release,
                  "control_evidence": self.root / (name + "-control-response.json")}
        self.workers.append(worker)
        return worker

    def _observe_copy(self, worker):
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            self.assertIsNone(worker["child"].poll(), "Verifier exited before COPY progress: " +
                              worker["log_path"].read_text(encoding="utf-8")[-2000:])
            journals = list(worker["output"].glob("*/report.json"))
            if journals:
                self.assertEqual(len(journals), 1)
                journal = json.loads(journals[0].read_text(encoding="utf-8"))
                if journal["phase"] == "restore" and journal["target"].get("container_id"):
                    observed = json.loads(self._sql(journal["target"]["container_id"], COPY_PROGRESS_SQL))
                    if observed:
                        self.assertEqual(len(observed), 1, observed)
                        self.assertGreater(observed[0]["tuples_processed"], 0)
                        self.assertLess(observed[0]["tuples_processed"], ROW_COUNT)
                        self.assertEqual(journal["status"], "INCOMPLETE", journal)
                        self.assertEqual(journal["exit_code"], 2)
                        return journals[0], journal, observed[0]
            time.sleep(0.05)
        self.fail("No active pg_restore COPY with processed rows appeared within 45 seconds")

    def _assert_foreign_alive(self, identifier):
        observed = self._inspect(identifier)
        self.assertEqual(observed["Id"], identifier)
        self.assertTrue(observed["State"]["Running"], "Owned-target recovery affected the foreign fixture")
        self.assertEqual(observed["Config"]["Labels"][FOREIGN_LABEL], self.foreign_token)

    def _allow_cleanup_after_response(self, worker, journal, response):
        """Called only after the real control SQL completed with exit zero."""
        identity = {"run_id": journal["run_id"], "container_id": journal["target"]["container_id"],
                    "worker_pid": worker["child"].pid}
        deadline = time.monotonic() + 15
        while not worker["cleanup_marker"].exists():
            self.assertIsNone(worker["child"].poll(), "Verifier exited before cleanup synchronization")
            if time.monotonic() >= deadline:
                self.fail("Verifier did not reach its bounded cleanup barrier")
            time.sleep(0.01)
        waiting = json.loads(worker["cleanup_marker"].read_text(encoding="utf-8"))
        self.assertEqual(waiting, {"identity": identity, "state": "waiting-for-control-response"})
        self.assertIsNone(worker["child"].poll())
        self.assertTrue(self._inspect(identity["container_id"])["State"]["Running"],
                        "Cleanup removed the container before control confirmation")
        evidence = {"identity": identity, "response": response, "control_command_exit_code": 0,
                    "cleanup_wait_observed": True, "target_running_before_release": True}
        _save(worker["control_evidence"], evidence)
        _save(worker["cleanup_release"], identity)
        return evidence

    def _healthy_retry(self, previous, foreign_id):
        """Use identical archive bytes; acknowledge the gate instead of killing COPY."""
        retry = self._launch("retry", defer_cleanup=True)
        path, journal, progress = self._observe_copy(retry)
        self.assertNotEqual(previous["run_id"], journal["run_id"])
        self.assertNotEqual(previous["target"]["container_id"], journal["target"]["container_id"])
        release = (f"SELECT pg_advisory_lock({self.lock_key}::bigint); SELECT pg_sleep(0.5); "
                   f"SELECT pg_advisory_unlock({self.lock_key}::bigint)")
        released = self._sql(journal["target"]["container_id"], release)
        self.assertEqual(released.strip(), "t", "Control SQL must confirm advisory lock release")
        control = self._allow_cleanup_after_response(retry, journal,
                    {"operation": "release-copy-gate", "advisory_unlock_confirmed": True})
        code = retry["child"].wait(timeout=30)
        report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(code, 0, report)
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["cleanup"]["status"], "PASS", report)
        self.assertEqual(report["cleanup"]["remaining"], [], report)
        self.assertEqual(report["archive_sha256"], previous["archive_sha256"])
        self._assert_foreign_alive(foreign_id)
        return report, progress, control

    def test_kill_cli_during_copy_writes_recovers_and_same_archive_retries(self):
        foreign_id = self._foreign_fixture()
        interrupted = self._launch("interrupted")
        path, journal, progress = self._observe_copy(interrupted)
        before = path.read_bytes()
        _save(self.root / "copy-before-kill.json", progress)
        self.assertIsNone(interrupted["child"].poll())
        _kill_worker_tree(interrupted["child"])
        self.assertNotEqual(interrupted["child"].returncode, 0)
        self.assertEqual(path.read_bytes(), before, "Killed verifier unexpectedly finalized its journal")
        recovered = DockerPostgres.cleanup_run(APPROVED_IMAGE, journal["run_id"], timeout_seconds=10)
        repeated = DockerPostgres.cleanup_run(APPROVED_IMAGE, journal["run_id"], timeout_seconds=10)
        for outcome in (recovered, repeated):
            self.assertEqual(outcome["status"], "PASS", outcome)
            self.assertEqual(outcome["remaining"], [], outcome)
        self._assert_foreign_alive(foreign_id)

        report, retry_progress, retry_control = self._healthy_retry(journal, foreign_id)
        self.assertEqual(path.read_bytes(), before, "Retry must preserve the interrupted run's evidence")
        _save(self.root / "restore-write-interruption.json", {
            "interrupted_run_id": journal["run_id"], "retry_run_id": report["run_id"],
            "archive_sha256": report["archive_sha256"], "copy_at_kill": progress,
            "child_returncode": interrupted["child"].returncode,
            "journal_status_after_kill": "INCOMPLETE", "recovery": recovered, "repeated": repeated,
            "retry_copy_progress": retry_progress, "retry_status": report["status"],
            "retry_control_response": retry_control,
            "retry_cleanup": report["cleanup"], "foreign_container_id": foreign_id,
            "foreign_retained_after_recovery_and_retry": True,
            "boundary": "Uncommitted COPY FROM processed rows observed before real CLI process-tree kill; not a committed-data-loss measurement."})

    def test_terminate_copy_backend_returns_incomplete_and_cleans_automatically(self):
        foreign_id = self._foreign_fixture()
        worker = self._launch("backend-terminated", defer_cleanup=True)
        path, journal, progress = self._observe_copy(worker)
        self.assertIsNone(worker["child"].poll(), "CLI must be alive when its COPY backend is terminated")
        backend_pid = progress["pid"]
        self.assertIs(type(backend_pid), int)
        self.assertGreater(backend_pid, 0)
        _save(self.root / "copy-before-backend-termination.json", progress)
        terminated = json.loads(self._sql(journal["target"]["container_id"],
                                f"SELECT to_json(pg_terminate_backend({backend_pid}, 5000))", timeout=8))
        self.assertIs(terminated, True, "PostgreSQL must confirm the observed backend terminated")
        control = self._allow_cleanup_after_response(worker, journal,
                    {"operation": "pg_terminate_backend", "backend_pid": backend_pid,
                     "timeout_ms": 5000, "terminated": terminated})
        code = worker["child"].wait(timeout=20)
        failed = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(code, 2, failed)
        self.assertEqual(failed["status"], "INCOMPLETE", failed)
        self.assertEqual(failed["exit_code"], 2)
        self.assertTrue(failed["errors"], failed)
        self.assertEqual(failed["errors"][0]["phase"], "restore", failed)
        self.assertEqual(failed["checks"], [], "Checks must not run after interrupted restore")
        self.assertNotIn("checks_seconds", failed["timings"])
        self.assertEqual(failed["cleanup"]["status"], "PASS", failed)
        self.assertEqual(failed["cleanup"]["remaining"], [], failed)
        self._assert_foreign_alive(foreign_id)
        retry, retry_progress, retry_control = self._healthy_retry(failed, foreign_id)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), failed)
        _save(self.root / "restore-backend-termination.json", {
            "failed_run_id": failed["run_id"], "copy_at_termination": progress,
            "pg_terminate_backend_result": terminated, "cli_exit_code": code,
            "termination_control_response": control,
            "final_status": failed["status"], "errors": failed["errors"],
            "downstream_checks": failed["checks"], "automatic_cleanup": failed["cleanup"],
            "retry_run_id": retry["run_id"], "retry_status": retry["status"],
            "retry_copy_progress": retry_progress, "archive_sha256": retry["archive_sha256"],
            "retry_control_response": retry_control,
            "foreign_container_id": foreign_id, "foreign_retained_after_failure_and_retry": True,
            "boundary": "Observed pg_restore COPY backend terminated while real verifier remained alive; uncommitted work, not a data-loss measurement."})

    def _cleanup_resources(self):
        errors = []
        for worker in self.workers:
            try:
                _kill_worker_tree(worker["child"])
            except Exception as error:
                errors.append(f"Worker cleanup: {type(error).__name__}: {error}")
            finally:
                worker["log"].close()
        run_ids = []
        for path in self.output.glob("*/*/report.json"):
            try:
                run_id = json.loads(path.read_text(encoding="utf-8"))["run_id"]
                if not re.fullmatch(r"[a-f0-9]{32}", run_id) or path.parent.name != run_id:
                    raise ValueError("Unexpected journal ownership")
                run_ids.append(run_id)
            except Exception as error:
                errors.append(f"Journal cleanup: {type(error).__name__}: {error}")
        source_path = self.root / "fixture" / "source.json"
        if source_path.exists():
            run_ids.append(json.loads(source_path.read_text(encoding="utf-8"))["source_run_id"])
        for run_id in run_ids:
            outcome = DockerPostgres.cleanup_run(APPROVED_IMAGE, run_id, timeout_seconds=10)
            if outcome["status"] != "PASS":
                errors.append(str(outcome))
        try:
            candidates = (self._docker("ps", "-a", "--no-trunc", "--filter",
                                       "label=" + FOREIGN_LABEL + "=" + self.foreign_token,
                                       "--format", "{{.ID}}").split() if self.foreign_attempted else [])
            for identifier in candidates:
                inspected = self._inspect(identifier)
                if (inspected["Id"] != identifier or inspected["Name"] != "/" + self.foreign_name
                        or inspected["Config"]["Labels"].get(FOREIGN_LABEL) != self.foreign_token):
                    raise RuntimeError("Foreign fixture ownership mismatch; deletion refused")
                self._docker("rm", "--force", identifier)
                remaining = self._docker("ps", "-a", "--no-trunc", "--filter", "id=" + identifier,
                                         "--format", "{{.ID}}").strip()
                if remaining:
                    raise RuntimeError("Owned foreign fixture remains")
        except Exception as error:
            errors.append(f"Foreign cleanup: {type(error).__name__}: {error}")
        _save(self.root / "test-cleanup.json", {"status": "INCOMPLETE" if errors else "PASS", "errors": errors})
        self.assertFalse(errors, "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
