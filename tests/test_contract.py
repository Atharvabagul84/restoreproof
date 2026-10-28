"""Contract and archive checks use real JSON files and archive bytes."""
import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path


class ContractTests(unittest.TestCase):
    def setUp(self):
        try:
            self.api = importlib.import_module("restoreproof.contract")
        except ImportError:
            self.fail("RestoreProof contract implementation is not available yet")
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.contract_path = self.root / "contract.json"
        self.archive = self.root / "fixture.dump"
        self.archive.write_bytes(b"PGDMP\x01synthetic-test-archive")

    def document(self):
        return {
            "version": 1,
            "backup": {
                "path": "fixture.dump",
                "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
            },
            "checks": [{"name": "event coverage", "sql": "SELECT 3", "expected": 3}],
            "freshness": {
                "sql": "SELECT max(committed_at) FROM heartbeat",
                "incident_at": "2026-10-06T12:00:00Z",
                "max_data_age_seconds": 60,
            },
        }

    def load(self, document):
        self.contract_path.write_text(json.dumps(document), encoding="utf-8")
        return self.api.load_contract(self.contract_path)

    def test_loads_defaults_and_resolves_archive_relative_to_contract(self):
        contract = self.load(self.document())
        self.assertEqual(contract.image, "postgres:17.11-bookworm")
        self.assertEqual(contract.max_restore_seconds, 300)
        self.assertEqual(contract.backup.path, "fixture.dump")
        self.assertIsNotNone(contract.freshness.incident_at.utcoffset())
        self.assertEqual(self.api.resolve_archive(contract, self.contract_path), self.archive.resolve())
        self.assertEqual(self.api.verify_archive(contract, self.contract_path), self.archive.resolve())

    def test_rejects_unknown_fields_at_each_model_boundary(self):
        for target in ("root", "backup", "check", "freshness"):
            with self.subTest(target=target):
                document = self.document()
                node = document if target == "root" else document["checks"][0] if target == "check" else document[target]
                node["unexpected"] = "secret-that-must-not-be-echoed"
                with self.assertRaises(self.api.ContractError) as caught:
                    self.load(document)
                self.assertNotIn("secret-that-must-not-be-echoed", str(caught.exception))

    def test_requires_a_valid_sha256(self):
        for value in (None, "", "x" * 64, "ab" * 31, 123):
            with self.subTest(value=value):
                document = self.document()
                if value is None:
                    del document["backup"]["sha256"]
                else:
                    document["backup"]["sha256"] = value
                with self.assertRaises(self.api.ContractError):
                    self.load(document)

    def test_rejects_naive_invalid_and_numeric_incident_dates(self):
        for value in ("2026-10-06T12:00:00", "2026-02-30T12:00:00Z", "yesterday", 1234, True, "0001-01-01T00:00:00+14:00", "9999-12-31T23:59:59-14:00"):
            with self.subTest(value=value):
                document = self.document()
                document["freshness"]["incident_at"] = value
                with self.assertRaises(self.api.ContractError):
                    self.load(document)

    def test_rejects_nonfinite_values_in_nested_expectations_and_thresholds(self):
        for field in ("expected", "freshness", "restore"):
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, value=value):
                    document = self.document()
                    if field == "expected":
                        document["checks"][0]["expected"] = {"nested": [value]}
                    elif field == "freshness":
                        document["freshness"]["max_data_age_seconds"] = value
                    else:
                        document["max_restore_seconds"] = value
                    with self.assertRaises(self.api.ContractError):
                        self.load(document)

    def test_rejects_overflowing_json_numbers(self):
        self.contract_path.write_text(json.dumps(self.document()).replace('"expected": 3', '"expected": 1e999'), encoding="utf-8")
        with self.assertRaises(self.api.ContractError):
            self.api.load_contract(self.contract_path)

    def test_rejects_duplicate_check_names_and_empty_checks(self):
        for checks in ([], [{"name": "same", "sql": "SELECT 1", "expected": 1}, {"name": "same", "sql": "SELECT 2", "expected": 2}]):
            document = self.document()
            document["checks"] = checks
            with self.assertRaises(self.api.ContractError):
                self.load(document)

    def test_rejects_reserved_report_identifiers(self):
        for name in ("freshness", "recovery-duration", "cleanup", "verification-run", " Freshness "):
            with self.subTest(name=name):
                document = self.document()
                document["checks"][0]["name"] = name
                with self.assertRaises(self.api.ContractError):
                    self.load(document)

    def test_rejects_empty_or_excessive_sql(self):
        for value in ("", " \n ", "x" * 16385):
            for field in ("check", "freshness"):
                with self.subTest(value_length=len(value), field=field):
                    document = self.document()
                    node = document["checks"][0] if field == "check" else document["freshness"]
                    node["sql"] = value
                    with self.assertRaises(self.api.ContractError):
                        self.load(document)

    def test_rejects_coerced_versions_types_and_out_of_bounds_thresholds(self):
        changes = [("version", True), ("version", "1"), ("version", 2), ("max_restore_seconds", "300"), ("max_restore_seconds", True), ("max_restore_seconds", 0), ("max_restore_seconds", 3601)]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                document = self.document()
                document[field] = value
                with self.assertRaises(self.api.ContractError):
                    self.load(document)
        for value in (-1, 86401, "60", True):
            document = self.document()
            document["freshness"]["max_data_age_seconds"] = value
            with self.assertRaises(self.api.ContractError):
                self.load(document)

    def test_allows_finite_fractional_thresholds_and_json_expectations(self):
        document = self.document()
        document["freshness"]["max_data_age_seconds"] = 0.5
        document["max_restore_seconds"] = 1.25
        document["checks"][0]["expected"] = {"ok": True, "data": [1, 1.5, None, "text"]}
        contract = self.load(document)
        self.assertEqual(contract.max_restore_seconds, 1.25)
        self.assertEqual(contract.checks[0].expected, document["checks"][0]["expected"])

    def test_restricts_images_to_approved_tag_and_optional_digest(self):
        for value in ("postgres:latest", "other/postgres:17.11-bookworm", "postgres:17.11-bookworm;echo bad"):
            document = self.document()
            document["image"] = value
            with self.assertRaises(self.api.ContractError):
                self.load(document)
        document = self.document()
        document["image"] = "postgres:17.11-bookworm@sha256:" + "a" * 64
        self.assertEqual(self.load(document).image, document["image"])

    def test_contract_read_is_bounded_and_malformed_json_is_safe(self):
        for payload in (b" " * (128 * 1024 + 1), b"{not-json", b"\xff"):
            self.contract_path.write_bytes(payload)
            with self.assertRaises(self.api.ContractError):
                self.api.load_contract(self.contract_path)

    def test_archive_verification_is_separate_from_loading(self):
        document = self.document()
        self.archive.unlink()
        contract = self.load(document)
        with self.assertRaises(self.api.ContractError):
            self.api.verify_archive(contract, self.contract_path)

    def test_rejects_wrong_magic_even_with_matching_checksum(self):
        self.archive.write_bytes(b"not-a-postgres-custom-archive")
        contract = self.load(self.document())
        with self.assertRaises(self.api.ContractError):
            self.api.verify_archive(contract, self.contract_path)

    def test_rejects_checksum_mismatch(self):
        contract = self.load(self.document())
        self.archive.write_bytes(b"PGDMPchanged-content")
        with self.assertRaises(self.api.ContractError):
            self.api.verify_archive(contract, self.contract_path)

    def test_rejects_archive_over_64_mib_before_hashing_it(self):
        contract = self.load(self.document())
        with self.archive.open("r+b") as stream:
            stream.truncate(64 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(self.api.ContractError, "64 MiB"):
            self.api.verify_archive(contract, self.contract_path)


if __name__ == "__main__":
    unittest.main()
