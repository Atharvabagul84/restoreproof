"""Independent committed-write evidence, tested with real files and values."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest


def write(sequence, *, write_id=None, timestamp=None):
    return {
        "write_id": write_id or f"write-{sequence:03d}",
        "sequence": sequence,
        "payload_sha256": hashlib.sha256(f"payload-{sequence}".encode()).hexdigest(),
        "acknowledged_at": timestamp or f"2026-10-06T12:00:{sequence % 60:02d}Z",
    }


class LedgerTests(unittest.TestCase):
    def setUp(self):
        try:
            self.ledger = importlib.import_module("restoreproof.ledger")
        except ImportError:
            self.fail("Independent ledger implementation is not available yet")
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "acknowledged.json"
        self.payload = {"version": 1, "writes": [write(1), write(2), write(3)]}

    def save(self, payload=None, *, raw=None):
        data = raw if raw is not None else json.dumps(payload or self.payload).encode()
        self.path.write_bytes(data)
        return hashlib.sha256(data).hexdigest()

    def compare(self, recovered, **kwargs):
        return self.ledger.compare_ledger(self.payload, recovered, **kwargs)

    def test_load_accepts_checksum_verified_independent_json_file(self):
        digest = self.save()
        self.assertEqual(self.ledger.load_ledger(self.path, digest), self.payload)

    def test_changed_file_fails_digest_even_when_valid_json(self):
        digest = self.save()
        self.path.write_bytes(self.path.read_bytes() + b" ")
        with self.assertRaisesRegex(self.ledger.LedgerError, "SHA-256"):
            self.ledger.load_ledger(self.path, digest)

    def test_load_missing_file_and_invalid_digest_are_safe_errors(self):
        for path, digest in ((self.path, "0" * 64), (self.path.parent, "0" * 64), (self.path, "private-token")):
            with self.subTest(path=path, digest=digest):
                with self.assertRaises(self.ledger.LedgerError) as caught:
                    self.ledger.load_ledger(path, digest)
                self.assertNotIn("private-token", str(caught.exception))

    def test_load_bounds_bytes_before_json_parse(self):
        digest = self.save(raw=b" " * (self.ledger.MAX_LEDGER_BYTES + 1))
        with self.assertRaisesRegex(self.ledger.LedgerError, "limit"):
            self.ledger.load_ledger(self.path, digest)

    def test_invalid_json_duplicate_keys_nonfinite_and_unknown_fields_rejected(self):
        variants = [
            b'{"version":1,"version":1,"writes":[]}',
            b'{"version":1,"writes":NaN}',
            b'{"version":1,"writes":Infinity}',
            b'{"version":1,"writes":[]',
            b'\xff',
            json.dumps({**self.payload, "secret": "private-data"}).encode(),
        ]
        for raw in variants:
            with self.subTest(raw=raw[:60]):
                digest = self.save(raw=raw)
                with self.assertRaises(self.ledger.LedgerError) as caught:
                    self.ledger.load_ledger(self.path, digest)
                self.assertNotIn("private-data", str(caught.exception))

    def test_expected_schema_is_strict_and_nonempty(self):
        variants = [
            {"version": True, "writes": [write(1)]},
            {"version": "1", "writes": [write(1)]},
            {"version": 2, "writes": [write(1)]},
            {"version": 1, "writes": []},
        ]
        for field, value in (("write_id", "bad id"), ("write_id", "x" * 65), ("sequence", True),
                             ("sequence", 1.0), ("sequence", "1"), ("sequence", 0),
                             ("sequence", 2**63), ("payload_sha256", "no"),
                             ("acknowledged_at", "2026-10-06T12:00:00"),
                             ("acknowledged_at", "2026-02-30T12:00:00Z"),
                             ("acknowledged_at", "0001-01-01T00:00:00+14:00"),
                             ("unexpected", "private-data")):
            record = write(1)
            record[field] = value
            variants.append({"version": 1, "writes": [record]})
        for payload in variants:
            with self.subTest(payload=payload):
                digest = self.save(payload)
                with self.assertRaises(self.ledger.LedgerError):
                    self.ledger.load_ledger(self.path, digest)

    def test_expected_ids_and_sequences_must_each_be_unique(self):
        for extra in (write(2, write_id="write-001"), write(1, write_id="another-id")):
            payload = {"version": 1, "writes": [write(1), extra]}
            digest = self.save(payload)
            with self.assertRaises(self.ledger.LedgerError):
                self.ledger.load_ledger(self.path, digest)

    def test_row_limit_rejects_expected_and_recovered_evidence(self):
        rows = [write(i + 1) for i in range(self.ledger.MAX_LEDGER_WRITES + 1)]
        result = self.ledger.compare_ledger({"version": 1, "writes": rows}, [])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(self.compare(rows)["status"], "INCOMPLETE")

    def test_complete_unordered_results_pass_without_sequence_gap_inference(self):
        self.payload["writes"] = [write(7), write(2), write(40)]
        result = self.compare([write(40), write(7), write(2)])
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["matched_count"], 3)
        self.assertEqual(result["missing_count"], 0)
        self.assertEqual(result["missing_write_ids"], [])

    def test_missing_interior_write_fails_despite_fresh_latest_acknowledgement(self):
        result = self.compare([write(1), write(3)], incident_at="2026-10-06T12:00:03Z")
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(result["missing_write_ids"], ["write-002"])
        self.assertEqual(result["matched_count"], 2)

    def test_trailing_loss_and_empty_restore_report_exact_known_missing_ids(self):
        for recovered, missing in (([write(1)], ["write-002", "write-003"]),
                                   ([], ["write-001", "write-002", "write-003"])):
            with self.subTest(recovered=recovered):
                result = self.compare(recovered)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["missing_write_ids"], missing)
                self.assertEqual(result["recovered_count"], len(recovered))

    def test_duplicate_recovered_ids_fail_without_silently_overwriting_rows(self):
        result = self.compare(self.payload["writes"] + [write(2)])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["duplicate_id_count"], 1)
        self.assertEqual(result["duplicate_write_ids"], ["write-002"])
        self.assertEqual(result["matched_count"], 2)

    def test_duplicate_sequences_across_distinct_recovered_ids_fail(self):
        recovered = deepcopy(self.payload["writes"])
        recovered[1]["sequence"] = 1
        result = self.compare(recovered)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["duplicate_sequence_count"], 1)
        self.assertEqual(result["duplicate_sequences"], [1])
        self.assertEqual(result["sequence_mismatch_write_ids"], ["write-002"])

    def test_payload_sequence_and_acknowledgement_mismatches_are_reported(self):
        recovered = deepcopy(self.payload["writes"])
        recovered[0]["payload_sha256"] = "0" * 64
        recovered[1]["sequence"] = 20
        recovered[2]["acknowledged_at"] = "2026-10-06T12:00:04Z"
        result = self.compare(recovered)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["payload_mismatch_write_ids"], ["write-001"])
        self.assertEqual(result["sequence_mismatch_write_ids"], ["write-002"])
        self.assertEqual(result["acknowledged_at_mismatch_write_ids"], ["write-003"])
        self.assertEqual(result["matched_count"], 0)

    def test_unexpected_recovered_write_is_explicit_closed_scope_failure(self):
        result = self.compare(self.payload["writes"] + [write(4)])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["unexpected_count"], 1)
        self.assertEqual(result["unexpected_write_ids"], ["write-004"])

    def test_unknown_or_invalid_recovered_evidence_is_incomplete_not_zero_loss(self):
        for recovered in (None, {}, "[]", [None], [{**write(1), "sequence": True}],
                          [{**write(1), "payload_sha256": float("nan")}],
                          [{**write(1), "acknowledged_at": None}]):
            with self.subTest(recovered=recovered):
                result = self.compare(recovered)
                self.assertEqual(result["status"], "INCOMPLETE")
                self.assertIsNone(result["missing_count"])
                self.assertIsNone(result["matched_count"])

    def test_invalid_expected_evidence_is_incomplete_when_compared_directly(self):
        result = self.ledger.compare_ledger({"version": 1, "writes": []}, [])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["reason"], "invalid_expected_ledger")

    def test_timestamp_offsets_and_hex_case_are_semantically_equal(self):
        recovered = deepcopy(self.payload["writes"])
        recovered[0]["acknowledged_at"] = "2026-10-06T17:30:01+05:30"
        recovered[0]["payload_sha256"] = recovered[0]["payload_sha256"].upper()
        self.assertEqual(self.compare(recovered)["status"], "PASS")

    def test_future_acknowledgement_is_incomplete_when_incident_is_known(self):
        result = self.compare(self.payload["writes"], incident_at="2026-10-06T12:00:02Z")
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["reason"], "acknowledgement_after_incident")
        self.assertTrue(result["timestamp_bound_checked"])

    def test_invalid_incident_is_incomplete_and_omission_is_disclosed(self):
        self.assertEqual(self.compare(self.payload["writes"], incident_at="invalid")["status"], "INCOMPLETE")
        self.assertFalse(self.compare(self.payload["writes"])["timestamp_bound_checked"])

    def test_report_lists_are_bounded_while_counts_remain_exact(self):
        self.payload["writes"] = [write(i) for i in range(1, 101)]
        result = self.compare([])
        self.assertEqual(result["missing_count"], 100)
        self.assertEqual(len(result["missing_write_ids"]), 25)
        self.assertTrue(result["ids_truncated"])
        self.assertEqual(result["name"], "committed-write-ledger")
        self.assertNotIn("rpo_seconds", result)
        self.assertLess(len(json.dumps(result)), 5000)


if __name__ == "__main__":
    unittest.main()
