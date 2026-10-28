"""Opt-in hosted-Linux private-daemon outage; never stops the system daemon."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch
import uuid

from isolated_daemon import IsolatedDaemon, client_environment, contained, docker, require_prerequisites
from daemon_worker import save
from restoreproof.contract import APPROVED_IMAGE
from restoreproof.demo import create_demo
from restoreproof.docker_postgres import DockerPostgres

OUTER_HOST = "unix:///var/run/docker.sock"
SENTINEL_LABEL = "io.restoreproof.daemon_drill_sentinel"


class DaemonIsolationGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.runtime = self.workspace / "runtime"
        self.evidence = self.workspace / "evidence"
        self.evidence.mkdir()

    def daemon(self):
        return IsolatedDaemon(self.workspace, self.runtime, self.evidence)

    def test_runtime_escape_is_rejected_before_filesystem_mutation(self):
        with self.assertRaises(ValueError):
            IsolatedDaemon(self.workspace, self.workspace.parent, self.evidence)

    def test_private_configuration_disables_host_network_mutations_and_image_store(self):
        daemon = self.daemon()
        args = daemon.command
        for value in ["--bridge=none", "--iptables=false", "--ip6tables=false", "--ip-masq=false",
                      "--ip-forward=false", "--userland-proxy=false", "--storage-driver=vfs",
                      "--exec-opt=native.cgroupdriver=cgroupfs"]:
            self.assertIn(value, args)
        for prefix in ["--host=unix://", "--data-root=", "--exec-root=", "--pidfile=", "--config-file="]:
            selected = next(value for value in args if value.startswith(prefix))
            self.assertTrue(Path(selected[len(prefix):]).is_relative_to(self.runtime))
        endpoints = [value.removeprefix("--containerd=") for value in args if value.startswith("--containerd=")]
        self.assertEqual(len(endpoints), 1, "Docker must never auto-discover the system containerd")
        self.assertTrue(endpoints[0], "An empty --containerd still enables Docker auto-discovery")
        self.assertTrue(Path(endpoints[0]).is_relative_to(self.runtime))
        self.assertIn("--containerd-namespace=rp-" + daemon.token, args)
        self.assertEqual(json.loads(daemon.config.read_text()), {"features": {"containerd-snapshotter": False}})

    def test_existing_runtime_is_not_adopted(self):
        self.runtime.mkdir()
        with self.assertRaises(FileExistsError):
            self.daemon()

    def test_client_environment_cannot_inherit_context_tls_or_other_daemon(self):
        with patch.dict(os.environ, {"DOCKER_CONTEXT": "production", "DOCKER_TLS_VERIFY": "1",
                                   "DOCKER_HOST": "tcp://unrelated", "DOCKER_CERT_PATH": "/secrets"}):
            environment = client_environment("unix:///private.sock", self.runtime / "client")
        self.assertEqual(environment["DOCKER_HOST"], "unix:///private.sock")
        self.assertEqual(environment["DOCKER_CONFIG"], str(self.runtime / "client"))
        for name in ["DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"]:
            self.assertNotIn(name, environment)

    def test_stop_without_owned_spawn_is_refused(self):
        with self.assertRaises(RuntimeError):
            self.daemon().stop()

    def test_pidfile_mismatch_refuses_to_signal_even_recorded_process(self):
        daemon = self.daemon()
        class RecordedProcess:
            pid = 12345
            def poll(self):
                return None
            def send_signal(self, value):
                raise AssertionError("unverified process was signaled")
        daemon.process = RecordedProcess()
        daemon.pidfile.write_text("98765")
        with self.assertRaises(RuntimeError):
            daemon.stop()

    def test_explicit_enable_on_non_linux_fails_prerequisites(self):
        with patch("isolated_daemon.sys.platform", "win32"), self.assertRaises(RuntimeError):
            require_prerequisites()

    def test_same_pid_with_changed_start_time_cannot_be_signaled(self):
        daemon = self.daemon()
        class RecordedProcess:
            pid = 12345
            def poll(self):
                return None
        daemon.process = RecordedProcess()
        daemon.pidfile.write_text("12345")
        daemon.identity = {"start": "10", "exe": "dockerd", "argv": []}
        with patch("isolated_daemon.process_identity", return_value={**daemon.identity, "start": "11"}):
            with patch("isolated_daemon.signal.pidfd_send_signal", create=True) as signal_call:
                with self.assertRaises(RuntimeError):
                    daemon.stop()
                signal_call.assert_not_called()

    def test_containerd_state_outside_private_runtime_is_rejected(self):
        daemon = self.daemon()
        daemon.containerd.config.write_text('root="/var/lib/containerd"\nstate="/run/containerd"\n[grpc]\naddress="/run/containerd/containerd.sock"\n')
        with self.assertRaises(ValueError):
            daemon.verify_runtime({"DockerRootDir": str(daemon.data_root), "Driver": "vfs", "CgroupDriver": "cgroupfs"})

    def test_containerd_uses_explicit_private_config_without_cri_tcp_or_imports(self):
        daemon = self.daemon()
        self.assertTrue(hasattr(daemon, "containerd"), "A separately owned private containerd is required")
        child = daemon.containerd
        self.assertEqual(child.command, ["containerd", "--config", str(child.config)])
        config = tomllib.loads(child.config.read_text())
        for value in [config["root"], config["state"], config["grpc"]["address"],
                      config["ttrpc"]["address"], config["debug"]["address"]]:
            self.assertTrue(Path(value).is_relative_to(self.runtime))
        self.assertEqual(config["imports"], [])
        self.assertEqual(config["grpc"]["tcp_address"], "")
        self.assertEqual(config["metrics"]["address"], "")
        self.assertIn("io.containerd.grpc.v1.cri", config["disabled_plugins"])

    def test_private_containerd_pidfile_mismatch_refuses_signal(self):
        daemon = self.daemon()
        self.assertTrue(hasattr(daemon, "containerd"), "A separately owned private containerd is required")
        class RecordedProcess:
            pid = 12345
            def poll(self):
                return None
        daemon.containerd.process = RecordedProcess()
        daemon.containerd.pidfile.write_text("98765")
        with patch("isolated_daemon.signal.pidfd_send_signal", create=True) as signal_call:
            with self.assertRaises(RuntimeError):
                daemon.containerd.stop()
            signal_call.assert_not_called()


@unittest.skipUnless(os.environ.get("RESTOREPROOF_DAEMON_INTEGRATION") == "1",
                     "requires explicitly enabled root Linux private-daemon drill")
class DaemonLossIntegrationTests(unittest.TestCase):
    def setUp(self):
        require_prerequisites()
        workspace = Path.cwd().resolve()
        token = uuid.uuid4().hex
        self.root = contained(workspace, Path(os.environ.get("RESTOREPROOF_EVIDENCE_DIR", "runs/daemon"))) / token
        self.root.mkdir(parents=True, exist_ok=False)
        self.daemon = IsolatedDaemon(workspace, workspace / ".rp-d" / token[:12], self.root)
        self.output = self.root / "runs"
        self.worker = self.worker_log = None
        self.sentinel_id = None
        self.sentinel_attempted = False
        self.sentinel_name = "restoreproof-daemon-sentinel-" + token
        self.sentinel_token = token
        self.outer_before = None
        self.addCleanup(self.cleanup_resources)

    def outer(self, *args, timeout=30):
        return docker(OUTER_HOST, self.daemon.client_config, *args, timeout=timeout)

    def inspect(self, identifier, *, outer=False):
        command = self.outer if outer else self.daemon.cli
        return json.loads(command("inspect", "--format", "{{json .}}", identifier))

    def create_sentinel(self):
        self.sentinel_attempted = True
        self.sentinel_id = self.outer(
            "create", "--name", self.sentinel_name, "--label", SENTINEL_LABEL + "=" + self.sentinel_token,
            "--network", "none", "--memory", "32m", "--cpus", "0.25", "--pids-limit", "16",
            "--read-only", "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=16777216",
            "--entrypoint", "/bin/sleep", APPROVED_IMAGE, "600").strip()
        self.assertRegex(self.sentinel_id, r"^[a-f0-9]{64}$")
        self.outer("start", self.sentinel_id)
        self.sentinel_before = self.inspect(self.sentinel_id, outer=True)

    def private_environment(self):
        environment = client_environment(self.daemon.host, self.daemon.client_config)
        source = str(Path(__file__).resolve().parents[1] / "src")
        environment["PYTHONPATH"] = source + os.pathsep + environment.get("PYTHONPATH", "")
        return environment

    def launch_worker(self, contract):
        self.marker, self.release = self.root / "checkpoint.json", self.root / "release"
        self.worker_log = (self.root / "verifier.log").open("wb")
        self.worker = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("daemon_worker.py").resolve()),
             str(contract), str(self.output), str(self.marker), str(self.release)],
            stdin=subprocess.DEVNULL, stdout=self.worker_log, stderr=self.worker_log,
            env=self.private_environment(), start_new_session=True)
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if self.marker.exists():
                return json.loads(self.marker.read_text())
            self.assertIsNone(self.worker.poll(), "Verifier exited before the restored-target checkpoint")
            time.sleep(0.1)
        self.fail("Verifier did not reach its restored-target checkpoint within 90 seconds")

    def assert_outer_unchanged(self):
        after = json.loads(self.outer("info", "--format", "{{json .}}"))
        self.assertEqual(after["ID"], self.outer_before["ID"])
        self.assertEqual(after["DockerRootDir"], self.outer_before["DockerRootDir"])
        sentinel = self.inspect(self.sentinel_id, outer=True)
        self.assertTrue(sentinel["State"]["Running"])
        self.assertEqual(sentinel["State"]["StartedAt"], self.sentinel_before["State"]["StartedAt"])
        self.assertEqual(sentinel["Config"]["Labels"][SENTINEL_LABEL], self.sentinel_token)

    def test_private_daemon_outage_preserves_incomplete_evidence_and_recovers(self):
        self.outer_before = json.loads(self.outer("info", "--format", "{{json .}}"))
        self.create_sentinel()
        initial = self.daemon.start()
        self.assertNotEqual(initial["ID"], self.outer_before["ID"])
        self.assertNotEqual(initial["DockerRootDir"], self.outer_before["DockerRootDir"])
        image_archive = self.daemon.runtime / "image.tar"
        self.outer("image", "save", "--output", str(image_archive), APPROVED_IMAGE, timeout=180)
        self.daemon.cli("image", "load", "--input", str(image_archive), timeout=180)
        source_image = json.loads(self.outer("image", "inspect", "--format", "{{json .}}", APPROVED_IMAGE))
        private_image = json.loads(self.daemon.cli("image", "inspect", "--format", "{{json .}}", APPROVED_IMAGE))
        self.assertEqual(source_image["Id"], private_image["Id"])
        save(self.root / "isolation.json", {"daemon_command": self.daemon.command,
             "outer_daemon_id": self.outer_before["ID"], "private_daemon_id": initial["ID"],
             "runtime": str(self.daemon.runtime), "containerd_paths_verified_private": True,
             "containerd_paths": self.daemon.containerd_paths,
             "containerd_pid": self.daemon.containerd.process.pid,
             "containerd_start_time": self.daemon.containerd.identity["start"],
             "containerd_command": self.daemon.containerd.command,
             "private_daemon": {key: initial.get(key) for key in
                 ["ServerVersion", "Driver", "CgroupDriver", "CgroupVersion", "DockerRootDir",
                  "KernelVersion", "OperatingSystem", "Architecture", "ContainerdCommit", "RuncCommit"]},
             "server_components": json.loads(self.daemon.cli("version", "--format", "{{json .Server.Components}}")),
             "image": {"reference": APPROVED_IMAGE, "source_id": source_image["Id"],
                       "source_repo_digests": source_image.get("RepoDigests", []),
                       "private_id": private_image["Id"], "private_repo_digests": private_image.get("RepoDigests", [])},
             "boundary": "Controlled SIGTERM of only the private daemon; live-restore is disabled."})
        with patch.dict(os.environ, self.private_environment(), clear=True):
            contract = create_demo(self.root / "fixtures", "healthy")
        checkpoint = self.launch_worker(contract)
        live = self.inspect(checkpoint["container_id"])
        self.assertTrue(live["State"]["Running"])
        self.assertEqual(live["Config"]["Labels"]["io.restoreproof.run_id"], checkpoint["run_id"])
        journal_path = self.output / checkpoint["run_id"] / "report.json"
        before = json.loads(journal_path.read_text())
        self.assertEqual((before["phase"], before["status"]), ("restore", "INCOMPLETE"))
        save(self.root / "journal-before-outage.json", before)
        stopped_pid, stopped_start_time = self.daemon.process.pid, self.daemon.identity["start"]
        self.daemon.stop()
        stop_returncode = self.daemon.process.returncode
        with self.assertRaises(RuntimeError):
            self.daemon.cli("info", timeout=5)
        self.assertIsNone(self.worker.poll(), "Verifier was not active at daemon outage")
        self.assert_outer_unchanged()
        self.release.touch()
        self.assertEqual(self.worker.wait(timeout=45), 2)
        failed_bytes = journal_path.read_bytes()
        failed = json.loads(failed_bytes)
        self.assertEqual((failed["status"], failed["cleanup"]["status"]), ("INCOMPLETE", "INCOMPLETE"), failed)
        self.assertIn(checkpoint["container_id"], failed["cleanup"]["remaining"])
        restarted = self.daemon.start()
        self.assertEqual(restarted["ID"], initial["ID"])
        retained = self.inspect(checkpoint["container_id"])
        self.assertEqual(retained["Id"], checkpoint["container_id"])
        with patch.dict(os.environ, self.private_environment(), clear=True):
            recovered = DockerPostgres.cleanup_run(APPROVED_IMAGE, checkpoint["run_id"])
            repeated = DockerPostgres.cleanup_run(APPROVED_IMAGE, checkpoint["run_id"])
        for outcome in [recovered, repeated]:
            self.assertEqual((outcome["status"], outcome["remaining"]), ("PASS", []), outcome)
        self.assertEqual(journal_path.read_bytes(), failed_bytes)
        self.assert_outer_unchanged()
        save(self.root / "daemon-loss.json", {"checkpoint": checkpoint,
             "stopped_daemon_pid": stopped_pid, "stopped_daemon_start_time": stopped_start_time,
             "stop_returncode": stop_returncode, "restarted_daemon_pid": self.daemon.process.pid,
             "restarted_daemon_start_time": self.daemon.identity["start"],
             "journal_status": failed["status"], "cleanup_during_outage": failed["cleanup"],
             "target_state_after_restart": retained["State"]["Status"], "recovered": recovered,
             "repeated": repeated, "outer_daemon_unchanged": True, "sentinel_unchanged": True,
             "boundary": "Real restored target at a test checkpoint; unavailable daemon API, not in-flight restore or power loss."})

    def cleanup_resources(self):
        errors = []
        if self.worker is not None and self.worker.poll() is None:
            try:
                if os.getpgid(self.worker.pid) != self.worker.pid:
                    raise RuntimeError("Verifier process group ownership changed")
                os.killpg(self.worker.pid, signal.SIGKILL)
                self.worker.wait(timeout=10)
            except Exception as error:
                errors.append("Worker cleanup: " + str(error))
        if self.worker_log is not None:
            self.worker_log.close()
        try:
            journals = list(self.output.glob("*/report.json"))
            if journals and (self.daemon.process is None or self.daemon.process.poll() is not None):
                self.daemon.start()
            with patch.dict(os.environ, self.private_environment(), clear=True):
                for journal in journals:
                    run_id = json.loads(journal.read_text())["run_id"]
                    if not re.fullmatch(r"[a-f0-9]{32}", run_id) or journal.parent.name != run_id:
                        raise RuntimeError("Unexpected run identity in cleanup journal")
                    outcome = DockerPostgres.cleanup_run(APPROVED_IMAGE, run_id)
                    if outcome["status"] != "PASS":
                        raise RuntimeError("Owned target cleanup remains incomplete")
        except Exception as error:
            errors.append("Private target cleanup: " + str(error))
        try:
            self.daemon.close()
        except Exception as error:
            errors.append("Private daemon cleanup: " + str(error))
        try:
            candidates = self.outer("ps", "-a", "--no-trunc", "--filter", "label=" + SENTINEL_LABEL + "=" + self.sentinel_token,
                                    "--format", "{{.ID}}").split() if self.sentinel_attempted else []
            for identifier in candidates:
                item = self.inspect(identifier, outer=True)
                if (item["Name"] != "/" + self.sentinel_name or item["Id"] != identifier
                        or item["Config"]["Labels"].get(SENTINEL_LABEL) != self.sentinel_token
                        or (self.sentinel_id is not None and identifier != self.sentinel_id)):
                    raise RuntimeError("Sentinel identity mismatch; refusing removal")
                self.outer("rm", "--force", identifier)
                if self.outer("ps", "-a", "--no-trunc", "--filter", "id=" + identifier, "--format", "{{.ID}}").strip():
                    raise RuntimeError("Owned sentinel remains after removal")
        except Exception as error:
            errors.append("Sentinel cleanup: " + str(error))
        save(self.root / "test-cleanup.json", {"status": "INCOMPLETE" if errors else "PASS", "errors": errors,
                                             "runtime_retained_for_ephemeral_runner_disposal": str(self.daemon.runtime)})
        self.assertFalse(errors, "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
