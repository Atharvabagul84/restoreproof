"""Real verifier CLI with a test-only barrier before its automatic cleanup.

The observer's Docker exec must return its PostgreSQL response before cleanup
can remove the container. Restore, checks, status evaluation and cleanup itself
remain the production implementations. No control-command failure is ignored.
"""
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

from restoreproof.cli import main as cli_main
from restoreproof.docker_postgres import DockerPostgres


def cleanup_after_release(cleanup, marker, release, identity, *, timeout_seconds=45):
    """Always attempt cleanup, but never report a missing handshake as success."""
    try:
        temporary = marker.with_suffix(".writing")
        temporary.write_text(json.dumps({"identity": identity,
                                         "state": "waiting-for-control-response"}) + "\n",
                             encoding="utf-8")
        temporary.replace(marker)
        deadline = time.monotonic() + timeout_seconds
        while not release.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("Control response was not acknowledged before cleanup deadline")
            time.sleep(0.01)
        if json.loads(release.read_text(encoding="utf-8")) != identity:
            raise ValueError("Cleanup release does not match this verifier and target")
    finally:
        outcome = cleanup()
    return outcome


def main(contract, output, marker, release):
    class CleanupControlledTarget(DockerPostgres):
        def cleanup(self):
            if self.container_id is None:
                return super().cleanup()
            identity = {"run_id": self.run_id, "container_id": self.container_id,
                        "worker_pid": os.getpid()}
            return cleanup_after_release(super().cleanup, marker, release, identity)

    with patch("restoreproof.docker_postgres.DockerPostgres", CleanupControlledTarget):
        return cli_main(["verify", str(contract), "--output", str(output)])


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit("Expected contract, output, cleanup marker and cleanup release paths")
    raise SystemExit(main(*(Path(arg) for arg in sys.argv[1:])))
