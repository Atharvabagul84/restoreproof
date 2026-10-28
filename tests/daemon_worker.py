"""Test-only verifier checkpoint after a real restore, before SQL checks."""
import json
import os
from pathlib import Path
import sys
import time

from restoreproof.docker_postgres import DockerPostgres
from restoreproof.engine import verify


def save(path, value):
    temporary = path.with_suffix(".writing")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main(contract, output, marker, release):
    class PausedAfterRestore(DockerPostgres):
        def restore(self, archive, expected_sha256):
            super().restore(archive, expected_sha256)
            save(marker, {"run_id": self.run_id, "container_id": self.container_id,
                          "worker_pid": os.getpid(), "checkpoint": "after-real-restore"})
            deadline = time.monotonic() + 120
            while not release.exists():
                if time.monotonic() >= deadline:
                    raise TimeoutError("Daemon drill checkpoint was not released.")
                time.sleep(0.05)
    report = verify(contract, output, backend_factory=PausedAfterRestore)
    print(json.dumps({"status": report["status"], "run_id": report["run_id"]}), flush=True)
    return report["exit_code"]


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("Expected contract, output, marker and release paths.")
    raise SystemExit(main(*(Path(arg) for arg in sys.argv[1:])))
