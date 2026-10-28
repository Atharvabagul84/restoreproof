"""Native Linux test daemon with private storage, runtime, socket and PID guards.

Docker documents multi-daemon operation as experimental. This helper is for an
explicitly enabled ephemeral runner, never a system Docker service controller.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import tomllib
import uuid


def require_prerequisites():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise RuntimeError("Explicit daemon drill requires an ephemeral Linux runner and root.")
    if not all(shutil.which(name) for name in ["docker", "dockerd", "containerd", "ctr", "runc"]):
        raise RuntimeError("Daemon drill requires docker, dockerd, containerd, ctr and runc on PATH.")
    if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
        raise RuntimeError("Daemon drill requires Linux PID-file-descriptor support.")


def contained(workspace, path):
    workspace, path = Path(workspace).resolve(), Path(path).resolve()
    if path == workspace or not path.is_relative_to(workspace):
        raise ValueError("Drill paths must remain strictly below the workspace.")
    return path


def client_environment(host, config):
    environment = os.environ.copy()
    for name in ["DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH", "DOCKER_API_VERSION"]:
        environment.pop(name, None)
    environment.update(DOCKER_HOST=host, DOCKER_CONFIG=str(config))
    return environment


def docker(host, config, *args, timeout=30):
    result = subprocess.run(["docker", "--host", host, "--config", str(config), *args],
                            stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
                            env=client_environment(host, config), check=False)
    if result.returncode or len(result.stdout) > 1024 * 1024 or len(result.stderr) > 1024 * 1024:
        raise RuntimeError("Bounded drill Docker operation failed; inspect curated daemon logs.")
    return result.stdout.decode("utf-8")


def process_identity(pid):
    root = Path("/proc") / str(pid)
    # Fields after the final ')' start at field 3; starttime is field 22.
    start = root.joinpath("stat").read_text().rsplit(")", 1)[1].split()[19]
    return {"start": start, "exe": str(root.joinpath("exe").resolve(strict=True)),
            "argv": root.joinpath("cmdline").read_bytes().rstrip(b"\0").split(b"\0")}


class IsolatedDaemon:
    def __init__(self, workspace, runtime, evidence):
        self.runtime = contained(workspace, runtime)
        self.evidence = contained(workspace, evidence)
        self.runtime.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.token = uuid.uuid4().hex
        self.config, self.pidfile = self.runtime / "daemon.json", self.runtime / "daemon.pid"
        self.data_root, self.exec_root = self.runtime / "data", self.runtime / "exec"
        self.client_config = self.runtime / "client"
        self.client_config.mkdir(mode=0o700)
        self.host = "unix://" + str(self.runtime / "docker.sock")
        self.config.write_text(json.dumps({"features": {"containerd-snapshotter": False}}))
        self.containerd = PrivateContainerd(self.runtime, self.evidence)
        self.command = ["dockerd", "--config-file=" + str(self.config), "--host=" + self.host,
                        "--containerd=" + str(self.containerd.socket),
                        "--data-root=" + str(self.data_root), "--exec-root=" + str(self.exec_root),
                        "--pidfile=" + str(self.pidfile), "--bridge=none", "--iptables=false",
                        "--ip6tables=false", "--ip-masq=false", "--ip-forward=false",
                        "--userland-proxy=false", "--storage-driver=vfs", "--live-restore=false",
                        "--shutdown-timeout=10", "--exec-opt=native.cgroupdriver=cgroupfs",
                        "--cgroup-parent=restoreproof-" + self.token,
                        "--containerd-namespace=rp-" + self.token,
                        "--containerd-plugins-namespace=rp-plugins-" + self.token]
        self.process = self.pidfd = self.identity = self.pump = None
        self.starts, self.ready = 0, False

    def cli(self, *args, timeout=30):
        return docker(self.host, self.client_config, *args, timeout=timeout)

    def _copy_log(self, path):
        remaining = 2 * 1024 * 1024
        with path.open("wb") as output, self.process.stdout as stream:
            while chunk := stream.read(4096):
                if remaining:
                    output.write(chunk[:remaining])
                    output.flush()
                    remaining = max(0, remaining - len(chunk))

    def _assert_owned(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("No live daemon spawned by this helper is available to signal.")
        if self.pidfile.exists():
            if self.pidfile.read_text().strip() != str(self.process.pid):
                raise RuntimeError("Private daemon PID file does not match the owned child.")
        elif self.ready:
            raise RuntimeError("Private daemon PID file disappeared; refusing a signal.")
        current = process_identity(self.process.pid)
        if (current != self.identity or current["argv"] != [os.fsencode(arg) for arg in self.command]
                or current["exe"] != str(Path(self.command[0]).resolve())):
            raise RuntimeError("Private daemon process identity changed; refusing a signal.")

    def start(self):
        require_prerequisites()
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError("The owned daemon is already running.")
        if len(os.fsencode(self.containerd.socket)) > 100:
            raise ValueError("Private runtime path is too long for its Unix sockets.")
        self.containerd.start()
        self.command[0] = str(Path(shutil.which("dockerd")).resolve())
        self.starts += 1
        self.ready = False
        self.process = subprocess.Popen(self.command, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        env=client_environment(self.host, self.client_config))
        self.pidfd = os.pidfd_open(self.process.pid)
        self.identity = process_identity(self.process.pid)
        self.pump = threading.Thread(target=self._copy_log,
                                     args=(self.evidence / f"daemon-{self.starts}.log",), daemon=True)
        self.pump.start()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Private daemon exited during startup; inspect its bounded log.")
            try:
                info = json.loads(self.cli("info", "--format", "{{json .}}", timeout=3))
                self._assert_owned()
                self.verify_runtime(info)
                self.ready = True
                return info
            except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError):
                time.sleep(0.2)
        raise RuntimeError("Private daemon did not become ready within 45 seconds.")

    def verify_runtime(self, info):
        if (Path(info["DockerRootDir"]).resolve() != self.data_root.resolve()
                or info.get("Driver") != "vfs" or info.get("CgroupDriver") != "cgroupfs"):
            raise RuntimeError("Private daemon storage or cgroup configuration was not applied.")
        config = tomllib.loads(self.containerd.config.read_text())
        for path in [config["root"], config["state"], config["grpc"]["address"]]:
            contained(self.runtime, path)
        if (config["grpc"]["address"] != str(self.containerd.socket)
                or "--containerd=" + str(self.containerd.socket) not in self.command):
            raise RuntimeError("Docker's explicit containerd endpoint does not match the private runtime.")
        self.containerd._assert_owned()
        self.containerd_paths = {"root": config["root"], "state": config["state"], "socket": config["grpc"]["address"]}

    def stop(self):
        self._assert_owned()
        if self.pidfd is None:
            raise RuntimeError("Owned daemon PID descriptor is unavailable.")
        signal.pidfd_send_signal(self.pidfd, signal.SIGTERM)
        try:
            self.process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            self._assert_owned()
            signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
            self.process.wait(timeout=10)
            raise RuntimeError("Private daemon required forced shutdown; outage evidence is incomplete.")
        finally:
            os.close(self.pidfd)
            self.pidfd = None
            self.pump.join(timeout=3)
        self.ready = False

    def _close_process(self):
        if self.process is not None and self.process.poll() is None:
            self.stop()
        elif self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None
        if self.pump is not None:
            self.pump.join(timeout=3)

    def close(self):
        try:
            self._close_process()
        finally:
            self.containerd._close_process()


class PrivateContainerd(IsolatedDaemon):
    """Reuse owned-process guards; never inherit host containerd configuration."""
    def __init__(self, runtime, evidence):
        self.runtime, self.evidence = runtime, evidence
        self.config, self.pidfile = runtime / "containerd.toml", runtime / "containerd.pid"
        self.socket = runtime / "containerd.sock"
        self.config.write_text(
            'version = 2\nimports = []\n'
            'disabled_plugins = ["io.containerd.grpc.v1.cri", "io.containerd.cri.v1.images", "io.containerd.cri.v1.runtime"]\n'
            'root = ' + json.dumps(str(runtime / "containerd-root")) + '\n'
            'state = ' + json.dumps(str(runtime / "containerd-state")) + '\n'
            '[grpc]\naddress = ' + json.dumps(str(self.socket)) + '\ntcp_address = ""\n'
            '[ttrpc]\naddress = ' + json.dumps(str(runtime / "ttrpc.sock")) + '\n'
            '[debug]\naddress = ' + json.dumps(str(runtime / "debug.sock")) + '\n'
            '[metrics]\naddress = ""\n', encoding="utf-8")
        self.command = ["containerd", "--config", str(self.config)]
        self.process = self.pidfd = self.identity = self.pump = None
        self.ready = False

    def start(self):
        if self.process is not None and self.process.poll() is None:
            self._assert_owned()
            return
        self.command[0] = str(Path(shutil.which("containerd")).resolve())
        self.process = subprocess.Popen(self.command, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.pidfd = os.pidfd_open(self.process.pid)
        self.identity = process_identity(self.process.pid)
        # containerd has no pidfile flag; this private ownership record supplements pidfd.
        self.pidfile.write_text(str(self.process.pid), encoding="ascii")
        self.pump = threading.Thread(target=self._copy_log, args=(self.evidence / "containerd.log",), daemon=True)
        self.pump.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            self._assert_owned()
            try:
                probe = subprocess.run(["ctr", "--address", str(self.socket), "version"],
                                       stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
                if probe.returncode == 0:
                    self.ready = True
                    return
            except subprocess.TimeoutExpired:
                pass
            time.sleep(0.1)
        raise RuntimeError("The owned private containerd did not become ready within 20 seconds.")
