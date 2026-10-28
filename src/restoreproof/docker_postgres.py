"""Bounded disposable PostgreSQL adapter; never adopts an existing target.

SQL and archives must be trusted. READ ONLY limits accidents, not arbitrary SQL
or malicious dump execution. Docker daemon access is a privileged capability.
"""
import json
import math
import re
import secrets
import time
from pathlib import Path

from .process import ProcessError, run_command

LABEL = "io.restoreproof.run_id"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
ARCHIVE_PATH = "/tmp/restoreproof.dump"
# The official entrypoint chowns PGDATA and drops to the postgres user; nothing else is granted.
POSTGRES_CAPABILITIES = ("CHOWN", "FOWNER", "SETGID", "SETUID")


def _reject_constant(value):
    raise ValueError("Non-finite values are not valid JSON.")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number exceeds the finite numeric range.")
    return number


class DockerPostgres:
    # Application adapters may retain ACLs after explicitly provisioning roles.
    restore_options = ("--no-owner", "--no-privileges")

    def __init__(self, image: str, run_id: str, timeout_seconds: float = 60):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("run_id must be 32 lowercase UUID hex characters.")
        if not re.fullmatch(r"postgres:17\.11-bookworm(?:@sha256:[a-f0-9]{64})?", image):
            raise ValueError("Use postgres:17.11-bookworm, optionally pinned by SHA256 digest.")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive and finite.")
        self.image, self.run_id, self.timeout_seconds = image, run_id, timeout_seconds
        self.name = "restoreproof-" + run_id
        self.container_id = self.image_id = None
        self._create_attempted = False
        self._recovery_authorized = False

    @classmethod
    def cleanup_run(cls, image: str, run_id: str, timeout_seconds: float = 60) -> dict:
        """Explicitly recover an owned run after a crash; never create a target."""
        adapter = cls(image, run_id, timeout_seconds)
        adapter._recovery_authorized = True
        return adapter.cleanup()

    def _run(self, *args, **kwargs):
        return run_command(["docker", *args], timeout=kwargs.pop("timeout", self.timeout_seconds), **kwargs)

    def _find(self, selector):
        raw = self._run("ps", "-a", "--no-trunc", "--filter", selector, "--format", "{{.ID}}")
        identifiers = raw.decode("utf-8").split()
        if any(not re.fullmatch(r"[a-f0-9]{64}", value) for value in identifiers):
            raise RuntimeError("Docker returned invalid container identities.")
        return identifiers

    def _inspect_owned(self, identifier):
        item = json.loads(self._run("inspect", "--format", "{{json .}}", identifier))
        if (item.get("Id") != identifier or item.get("Name", "").lstrip("/") != self.name
                or item.get("Config", {}).get("Labels", {}).get(LABEL) != self.run_id
                or (self.container_id is not None and identifier != self.container_id)):
            raise RuntimeError("Container ownership or identity verification failed.")
        return item

    def _owned(self):
        if not self.container_id:
            raise RuntimeError("Create a disposable target before this operation.")
        self._inspect_owned(self.container_id)
        return self.container_id

    def create(self) -> dict:
        if self._create_attempted or self._find("name=^/" + self.name + "$"):
            raise RuntimeError("A target already exists; existing containers are never adopted.")
        self._create_attempted = True
        deadline = time.monotonic() + self.timeout_seconds
        raw = self._run(
            "create", "--name", self.name, "--label", f"{LABEL}={self.run_id}",
            "--network", "none", "--memory", "512m", "--cpus", "1", "--pids-limit", "128",
            "--cap-drop", "ALL", *(arg for cap in POSTGRES_CAPABILITIES for arg in ("--cap-add", cap)),
            "--security-opt", "no-new-privileges",
            "--tmpfs", "/var/lib/postgresql/data:rw,noexec,nosuid,size=268435456",
            "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_DB=restoreproof", self.image,
            env={"POSTGRES_PASSWORD": secrets.token_urlsafe(32)},
        )
        identifier = raw.decode("ascii").strip()
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise RuntimeError("Docker did not return a valid created container ID.")
        self.container_id = identifier
        self.image_id = self._inspect_owned(identifier)["Image"]
        self._run("start", identifier)
        while time.monotonic() < deadline:
            try:
                self._run("exec", identifier, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "restoreproof",
                          timeout=max(0.01, deadline - time.monotonic()))
                return {"container_id": identifier, "image_id": self.image_id}
            except ProcessError:
                time.sleep(min(0.2, max(0, deadline - time.monotonic())))
        raise RuntimeError("Disposable PostgreSQL did not become ready within the deadline.")

    def _sql(self, sql):
        if not isinstance(sql, str) or len(sql.encode("utf-8")) > 65536:
            raise ValueError("Trusted SQL must fit within 64 KiB.")
        return self._run("exec", "-i", self._owned(), "psql", "-XqAt", "-v", "ON_ERROR_STOP=1",
                         "-U", "postgres", "-d", "restoreproof", input_data=sql.encode("utf-8"))

    def execute(self, sql: str) -> None:
        """Execute trusted fixture SQL; never accepts a user-selected database."""
        self._sql(sql)

    def query(self, sql: str):
        """Read one JSON result from trusted SQL; not an arbitrary-SQL sandbox."""
        milliseconds = max(1, int(self.timeout_seconds * 1000))
        result = self._sql(f"BEGIN READ ONLY;\nSET LOCAL statement_timeout = {milliseconds};\n{sql.rstrip().rstrip(';')};\nROLLBACK;\n")
        return json.loads(result.decode("utf-8"), parse_constant=_reject_constant, parse_float=_finite_float)

    def restore(self, archive: Path, expected_sha256: str) -> None:
        """Restore only copied bytes matching the digest in the validated contract."""
        if not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", expected_sha256):
            raise ValueError("Expected SHA-256 must contain exactly 64 hexadecimal characters.")
        path = Path(archive).resolve(strict=True)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES:
            raise ValueError("Archive must be a regular file between 1 byte and 64 MiB.")
        identifier = self._owned()
        self._run("cp", str(path), f"{identifier}:{ARCHIVE_PATH}")
        digest = self._run("exec", self._owned(), "sha256sum", ARCHIVE_PATH).decode("ascii").split()
        if len(digest) != 2 or digest[1] != ARCHIVE_PATH or digest[0] != expected_sha256.lower():
            raise ValueError("Copied archive SHA-256 does not match the validated contract.")
        self._run("exec", self._owned(), "pg_restore", "--exit-on-error", "--single-transaction",
                  *self.restore_options, "--username", "postgres", "--dbname", "restoreproof", ARCHIVE_PATH)

    def dump(self, path: Path) -> None:
        destination = Path(path).resolve()
        if destination.exists() or not destination.parent.is_dir():
            raise ValueError("Dump destination must be new and its parent must exist.")
        self._run("exec", self._owned(), "pg_dump", "--format=custom", "--username", "postgres",
                  "--dbname", "restoreproof", "--file", ARCHIVE_PATH)
        size = int(self._run("exec", self._owned(), "stat", "-c", "%s", ARCHIVE_PATH))
        if not 0 < size <= MAX_ARCHIVE_BYTES:
            raise ValueError("Generated archive exceeds the 64 MiB limit or is empty.")
        self._run("cp", f"{self._owned()}:{ARCHIVE_PATH}", str(destination))

    def cleanup(self) -> dict:
        remaining = [self.container_id or self.name]
        try:
            candidates = self._find("name=^/" + self.name + "$")
            if not candidates:
                remaining = self._find("label=" + LABEL + "=" + self.run_id)
                if self.container_id:
                    remaining = sorted(set(remaining + self._find("id=" + self.container_id)))
                if remaining:
                    raise RuntimeError("Run containers were renamed or are ambiguous; cleanup stopped.")
                return {"status": "PASS", "remaining": [], "message": "Container absence verified."}
            if not (self._create_attempted or self._recovery_authorized) or len(candidates) != 1:
                raise RuntimeError("Existing target was not created by this adapter.")
            identifier = candidates[0]
            remaining = [identifier]
            if self.container_id is None:
                self.container_id = identifier
            self._inspect_owned(identifier)
            self._run("rm", "--force", identifier)
            remaining = self._find("id=" + identifier)
            if remaining:
                raise RuntimeError("Container remains after removal.")
            return {"status": "PASS", "remaining": [], "message": "Owned container removed; absence verified."}
        except (RuntimeError, ValueError, OSError, KeyError, TypeError):
            return {"status": "INCOMPLETE", "remaining": remaining,
                    "message": "Cleanup could not verify ownership, removal or daemon availability; inspect the recorded target."}
