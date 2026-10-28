import json
import hashlib
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from restoreproof.docker_postgres import DockerPostgres
    from restoreproof.process import ProcessError
except ImportError:
    DockerPostgres, ProcessError = None, RuntimeError

RUN = "a" * 32
CID = "b" * 64
IMAGE = "postgres:17.11-bookworm"
DIGEST = hashlib.sha256(b"PGDMPfixture").hexdigest()


class DockerFixture:
    """Minimal Docker command boundary; production lifecycle logic remains real."""
    def __init__(self):
        self.present = False
        self.label = RUN
        self.identity = CID
        self.calls = []
        self.output = b'{"rows": 2}\n'
        self.fail_create = False
        self.daemon_down = False
        self.refuse_remove = False
        self.archive_size = 12
        self.name = "restoreproof-" + RUN
        self.copied_archive = b""
        self.change_copied_bytes = False

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.daemon_down:
            raise ProcessError("Command failed.", returncode=1)
        action = args[1]
        if action == "ps":
            selector = args[args.index("--filter") + 1]
            matches = (selector == "name=^/" + self.name + "$" or selector == "id=" + self.identity
                       or selector == "label=io.restoreproof.run_id=" + self.label)
            return (self.identity + "\n").encode() if self.present and matches else b""
        if action == "create":
            self.present = True
            if self.fail_create:
                raise ProcessError("Command timed out.")
            return (self.identity + "\n").encode()
        if action == "inspect":
            return json.dumps({"Id": self.identity, "Name": self.name,
                               "Config": {"Labels": {"io.restoreproof.run_id": self.label}},
                               "Image": "sha256:" + "c" * 64}).encode()
        if action == "rm":
            self.present = self.refuse_remove
            return b""
        if action == "exec" and "psql" in args:
            return self.output
        if action == "exec" and "stat" in args:
            return str(self.archive_size).encode()
        if action == "exec" and "sha256sum" in args:
            return (hashlib.sha256(self.copied_archive).hexdigest() + "  /tmp/restoreproof.dump\n").encode()
        if action == "cp" and args[-2].startswith(CID + ":"):
            Path(args[-1]).write_bytes(b"PGDMPfixture")
        elif action == "cp":
            self.copied_archive = Path(args[-2]).read_bytes() + (b"changed" if self.change_copied_bytes else b"")
        return b""


class DockerPostgresTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(DockerPostgres, "owned Docker PostgreSQL backend is missing")
        self.fixture = DockerFixture()
        self.runner = patch("restoreproof.docker_postgres.run_command", self.fixture)
        self.runner.start()
        self.addCleanup(self.runner.stop)
        self.backend = DockerPostgres(IMAGE, RUN, timeout_seconds=1)

    def test_rejects_untrusted_names_images_and_timeouts(self):
        for run_id in ["../target", "-f", "a" * 31, "A" * 32]:
            with self.subTest(run_id=run_id), self.assertRaises(ValueError):
                DockerPostgres(IMAGE, run_id)
        for image in ["alpine", "postgres:latest", IMAGE + " --privileged"]:
            with self.subTest(image=image), self.assertRaises(ValueError):
                DockerPostgres(image, RUN)
        with self.assertRaises(ValueError):
            DockerPostgres(IMAGE, RUN, timeout_seconds=0)

    def test_create_has_no_host_access_and_returns_observed_identity(self):
        result = self.backend.create()
        self.assertEqual(result, {"container_id": CID, "image_id": "sha256:" + "c" * 64})
        args, kwargs = next(call for call in self.fixture.calls if call[0][1] == "create")
        self.assertEqual(args[args.index("--network") + 1], "none")
        self.assertIn("--tmpfs", args)
        self.assertTrue(all(flag in args for flag in ["--memory", "--cpus", "--pids-limit"]))
        self.assertEqual(args[args.index("--cap-drop") + 1], "ALL")
        self.assertEqual({args[i + 1] for i, flag in enumerate(args) if flag == "--cap-add"},
                         {"CHOWN", "FOWNER", "SETGID", "SETUID"})
        self.assertEqual(args[args.index("--security-opt") + 1], "no-new-privileges")
        self.assertFalse(any(flag in args for flag in ["-p", "--publish", "-v", "--volume", "--mount", "--privileged"]))
        self.assertIn("POSTGRES_PASSWORD", kwargs["env"])
        self.assertNotIn(kwargs["env"]["POSTGRES_PASSWORD"], " ".join(args))

    def test_preexisting_name_is_never_adopted_or_deleted(self):
        self.fixture.present = True
        with self.assertRaises(RuntimeError):
            self.backend.create()
        self.assertEqual(self.backend.cleanup()["status"], "INCOMPLETE")
        self.assertFalse(any(args[1] == "rm" for args, _ in self.fixture.calls))

    def test_query_uses_readonly_transaction_and_exact_json(self):
        self.backend.create()
        self.assertEqual(self.backend.query("SELECT json_build_object('rows', 2)"), {"rows": 2})
        args, kwargs = self.fixture.calls[-1]
        self.assertIn("-XqAt", args)
        self.assertIn("ON_ERROR_STOP=1", args)
        sql = kwargs["input_data"].decode()
        self.assertIn("BEGIN READ ONLY", sql)
        self.assertIn("statement_timeout", sql)
        self.assertIn("ROLLBACK", sql)
        self.assertNotIn("-h", args)
        self.fixture.output = b"{}\n{}\n"
        with self.assertRaises(ValueError):
            self.backend.query("SELECT '{}'::json")

    def test_query_rejects_nonstandard_json_and_oversized_sql(self):
        self.backend.create()
        for value in [b"NaN", b"Infinity", b"-Infinity", b'{"bad":NaN}', b"1e999"]:
            self.fixture.output = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.backend.query("SELECT 1")
        with self.assertRaises(ValueError):
            self.backend.execute("x" * (65536 + 1))

    def test_archive_size_is_checked_before_copy(self):
        self.assertIn("expected_sha256", inspect.signature(self.backend.restore).parameters)
        self.backend.create()
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "large.dump"
            with archive.open("wb") as output:
                output.truncate(64 * 1024 * 1024 + 1)
            with self.assertRaises(ValueError):
                self.backend.restore(archive, DIGEST)
        self.assertFalse(any(args[1] == "cp" for args, _ in self.fixture.calls))

    def test_restore_copies_only_to_owned_container_and_uses_transaction(self):
        self.assertIn("expected_sha256", inspect.signature(self.backend.restore).parameters)
        self.backend.create()
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "fixture.dump"
            archive.write_bytes(b"PGDMPfixture")
            self.backend.restore(archive, DIGEST)
        cp = next(args for args, _ in self.fixture.calls if args[1] == "cp")
        self.assertTrue(cp[-1].startswith(CID + ":/tmp/"))
        restore = next(args for args, _ in self.fixture.calls if "pg_restore" in args)
        self.assertTrue(all(flag in restore for flag in ["--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges"]))
        actions = [args for args, _ in self.fixture.calls]
        self.assertLess(next(i for i, args in enumerate(actions) if "sha256sum" in args),
                        next(i for i, args in enumerate(actions) if "pg_restore" in args))

    def test_changed_copied_bytes_are_rejected_before_restore(self):
        self.assertIn("expected_sha256", inspect.signature(self.backend.restore).parameters)
        self.backend.create()
        self.fixture.change_copied_bytes = True
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "fixture.dump"
            archive.write_bytes(b"PGDMPfixture")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                self.backend.restore(archive, DIGEST)
        self.assertFalse(any("pg_restore" in args for args, _ in self.fixture.calls))

    def test_invalid_expected_digest_is_rejected_before_copy(self):
        self.assertIn("expected_sha256", inspect.signature(self.backend.restore).parameters)
        for value in ["", "z" * 64, DIGEST + " extra", None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.backend.restore(Path("unused.dump"), value)
        self.assertFalse(self.fixture.calls)

    def test_execute_and_dump_only_use_created_container(self):
        with self.assertRaises(RuntimeError):
            self.backend.execute("SELECT 1")
        self.backend.create()
        self.backend.execute("SELECT 1")
        with tempfile.TemporaryDirectory() as temporary:
            self.backend.dump(Path(temporary) / "fixture.dump")
        self.assertTrue(any("pg_dump" in args for args, _ in self.fixture.calls))
        cp = [args for args, _ in self.fixture.calls if args[1] == "cp"][-1]
        self.assertTrue(cp[-2].startswith(CID + ":/tmp/"))

    def test_dump_rejects_oversized_archive_before_host_copy(self):
        self.backend.create()
        self.fixture.archive_size = 64 * 1024 * 1024 + 1
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "fixture.dump"
            with self.assertRaises(ValueError):
                self.backend.dump(destination)
            self.assertFalse(destination.exists())

    def test_cleanup_verifies_absence_and_never_prunes(self):
        self.backend.create()
        result = self.backend.cleanup()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["remaining"], [])
        removal = next(args for args, _ in self.fixture.calls if args[1] == "rm")
        self.assertEqual(removal[-1], CID)
        self.assertFalse(any("prune" in args for args, _ in self.fixture.calls))

    def test_wrong_label_and_replaced_identity_are_not_deleted(self):
        for attribute, value in [("label", "foreign"), ("identity", "d" * 64)]:
            with self.subTest(attribute=attribute):
                self.fixture.present = False
                self.fixture.label, self.fixture.identity = RUN, CID
                backend = DockerPostgres(IMAGE, RUN)
                backend.create()
                setattr(self.fixture, attribute, value)
                self.assertEqual(backend.cleanup()["status"], "INCOMPLETE")
        self.assertFalse(any(args[1] == "rm" for args, _ in self.fixture.calls))

    def test_daemon_failure_is_not_reported_as_absence(self):
        self.backend.create()
        self.fixture.daemon_down = True
        self.assertEqual(self.backend.cleanup()["status"], "INCOMPLETE")

    def test_incomplete_removal_is_reported(self):
        self.backend.create()
        self.fixture.refuse_remove = True
        self.assertEqual(self.backend.cleanup()["remaining"], [CID])

    def test_timed_out_create_is_still_discovered_and_cleaned(self):
        self.fixture.fail_create = True
        with self.assertRaises(ProcessError):
            self.backend.create()
        self.assertEqual(self.backend.cleanup()["status"], "PASS")

    def test_explicit_recovery_removes_matching_owned_run(self):
        self.assertTrue(hasattr(DockerPostgres, "cleanup_run"), "explicit crash recovery API is missing")
        self.fixture.present = True
        result = DockerPostgres.cleanup_run(IMAGE, RUN)
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(self.fixture.present)
        removal = next(args for args, _ in self.fixture.calls if args[1] == "rm")
        self.assertEqual(removal[-1], CID)

    def test_explicit_recovery_reports_verified_absence(self):
        self.assertTrue(hasattr(DockerPostgres, "cleanup_run"), "explicit crash recovery API is missing")
        self.assertEqual(DockerPostgres.cleanup_run(IMAGE, RUN)["status"], "PASS")
        self.assertFalse(any(args[1] == "rm" for args, _ in self.fixture.calls))

    def test_explicit_recovery_refuses_foreign_matching_name(self):
        self.assertTrue(hasattr(DockerPostgres, "cleanup_run"), "explicit crash recovery API is missing")
        self.fixture.present = True
        self.fixture.label = "foreign"
        self.assertEqual(DockerPostgres.cleanup_run(IMAGE, RUN)["status"], "INCOMPLETE")
        self.assertTrue(self.fixture.present)
        self.assertFalse(any(args[1] == "rm" for args, _ in self.fixture.calls))

    def test_explicit_recovery_reports_renamed_run_without_deleting(self):
        self.fixture.present = True
        self.fixture.name = "renamed-owned-container"
        result = DockerPostgres.cleanup_run(IMAGE, RUN)
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["remaining"], [CID])
        self.assertTrue(self.fixture.present)
        self.assertFalse(any(args[1] == "rm" for args, _ in self.fixture.calls))


if __name__ == "__main__":
    unittest.main()
