"""Compare a sealed acknowledgement ledger with recovered, scoped writes.

The ledger must be recorded independently of the backup. Its digest detects
changed bytes; it does not prove who recorded it or that its coverage is complete.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, ValidationError, field_validator, model_validator

from .contract import StrictModel, parse_timestamp

MAX_LEDGER_BYTES = 2 * 1024 * 1024
MAX_LEDGER_WRITES = 5000
REPORT_ID_LIMIT = 25
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class LedgerError(ValueError):
    """Safe external-evidence error without supplied paths or file contents."""


class LedgerWrite(StrictModel):
    write_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")]
    sequence: Annotated[int, Field(gt=0, le=2**63 - 1)]
    payload_sha256: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]
    acknowledged_at: Annotated[str, Field(min_length=1, max_length=64)]

    @field_validator("payload_sha256")
    @classmethod
    def canonical_digest(cls, value: str) -> str:
        return value.lower()

    @field_validator("acknowledged_at")
    @classmethod
    def aware_acknowledgement(cls, value: str) -> str:
        parse_timestamp(value)
        return value


class LedgerDocument(StrictModel):
    version: Literal[1]
    writes: Annotated[list[LedgerWrite], Field(min_length=1, max_length=MAX_LEDGER_WRITES)]

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be a strict integer")
        return value

    @model_validator(mode="after")
    def unambiguous_expected_writes(self) -> LedgerDocument:
        if len({row.write_id for row in self.writes}) != len(self.writes):
            raise ValueError("Expected write IDs must be unique")
        if len({row.sequence for row in self.writes}) != len(self.writes):
            raise ValueError("Expected sequences must be unique")
        return self


_RECOVERED = TypeAdapter(Annotated[list[LedgerWrite], Field(max_length=MAX_LEDGER_WRITES)])


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def load_ledger(path: Path, expected_sha256: str) -> dict:
    """Load at most 2 MiB from a regular file; callers resolve contract paths."""
    if type(expected_sha256) is not str or not _SHA256.fullmatch(expected_sha256):
        raise LedgerError("Ledger SHA-256 must contain 64 hexadecimal characters.")
    try:
        path = Path(path)
        if not path.is_file():
            raise LedgerError("Ledger must be an existing regular file.")
        with path.open("rb") as stream:
            data = stream.read(MAX_LEDGER_BYTES + 1)
        if len(data) > MAX_LEDGER_BYTES:
            raise LedgerError("Ledger exceeds the 2 MiB limit.")
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected_sha256.lower()):
            raise LedgerError("Ledger SHA-256 does not match the contract.")
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
                             parse_constant=_reject_constant)
        return LedgerDocument.model_validate(payload).model_dump(mode="json")
    except LedgerError:
        raise
    except OSError:
        raise LedgerError("Ledger could not be read.") from None
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise LedgerError("Ledger is invalid; check its schema, types and bounds.") from None


_DIFFERENCES = {
    "missing": "missing_write_ids",
    "unexpected": "unexpected_write_ids",
    "duplicate_id": "duplicate_write_ids",
    "duplicate_sequence": "duplicate_sequences",
    "payload_mismatch": "payload_mismatch_write_ids",
    "sequence_mismatch": "sequence_mismatch_write_ids",
    "acknowledged_at_mismatch": "acknowledged_at_mismatch_write_ids",
}


def _empty_report() -> dict:
    report = {"name": "committed-write-ledger", "status": "INCOMPLETE",
              "reason": "invalid_expected_ledger", "expected_count": None,
              "recovered_count": None, "matched_count": None,
              "timestamp_bound_checked": False, "report_id_limit": REPORT_ID_LIMIT,
              "ids_truncated": False}
    for category, list_key in _DIFFERENCES.items():
        report[category + "_count"] = None
        report[list_key] = []
    return report


def _differences(expected: list[LedgerWrite], recovered: list[LedgerWrite]) -> tuple[dict, int]:
    expected_by_id = {row.write_id: row for row in expected}
    id_counts = Counter(row.write_id for row in recovered)
    sequence_counts = Counter(row.sequence for row in recovered)
    actual_by_id = {row.write_id: row for row in recovered if id_counts[row.write_id] == 1}
    groups = {
        "missing": set(expected_by_id) - set(id_counts),
        "unexpected": set(id_counts) - set(expected_by_id),
        "duplicate_id": {key for key, count in id_counts.items() if count > 1},
        "duplicate_sequence": {key for key, count in sequence_counts.items() if count > 1},
        "payload_mismatch": set(), "sequence_mismatch": set(), "acknowledged_at_mismatch": set(),
    }
    matched = 0
    for write_id in set(expected_by_id) & set(actual_by_id):
        wanted, actual = expected_by_id[write_id], actual_by_id[write_id]
        mismatch = {
            "payload_mismatch": wanted.payload_sha256 != actual.payload_sha256,
            "sequence_mismatch": wanted.sequence != actual.sequence,
            "acknowledged_at_mismatch": parse_timestamp(wanted.acknowledged_at) != parse_timestamp(actual.acknowledged_at),
        }
        for category, differs in mismatch.items():
            if differs:
                groups[category].add(write_id)
        matched += not any(mismatch.values())
    return groups, matched


def compare_ledger(payload: object, recovered: object, *, incident_at: object = None) -> dict:
    """Compare exact write identities, independent of query order or timestamps.

No RPO duration is inferred. ``incident_at`` checks the explicit experiment
cutoff; omitting it is disclosed by ``timestamp_bound_checked: false``.
"""
    report = _empty_report()
    try:
        expected = LedgerDocument.model_validate(payload).writes
    except (ValueError, TypeError, RecursionError):
        return report
    report["expected_count"] = len(expected)
    try:
        actual = _RECOVERED.validate_python(recovered, strict=True)
    except (ValueError, TypeError, RecursionError):
        report["reason"] = "invalid_recovered_writes"
        return report
    report["recovered_count"] = len(actual)
    if incident_at is not None:
        try:
            incident = parse_timestamp(incident_at)
        except (ValueError, TypeError, OverflowError):
            report["reason"] = "invalid_incident_timestamp"
            return report
        report["timestamp_bound_checked"] = True
        if any(parse_timestamp(row.acknowledged_at) > incident for row in expected + actual):
            report["reason"] = "acknowledgement_after_incident"
            return report
    groups, report["matched_count"] = _differences(expected, actual)
    for category, list_key in _DIFFERENCES.items():
        values = sorted(groups[category])
        report[category + "_count"] = len(values)
        report[list_key] = values[:REPORT_ID_LIMIT]
        report["ids_truncated"] |= len(values) > REPORT_ID_LIMIT
    report["status"] = "FAIL" if any(groups.values()) else "PASS"
    report["reason"] = "write_set_differs" if report["status"] == "FAIL" else "all_known_writes_match"
    return report
