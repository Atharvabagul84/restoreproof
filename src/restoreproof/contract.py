"""Bounded, strict configuration and custom-format archive preflight.

SQL is trusted project configuration. The database adapter, not a SQL parser
here, must enforce the read-only verification boundary.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator, model_validator

MAX_CONTRACT_BYTES = 128 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
RESERVED_CHECK_NAMES = frozenset({"freshness", "recovery-duration", "cleanup", "verification-run", "committed-write-ledger"})
APPROVED_IMAGE = "postgres:17.11-bookworm"
IMAGE_PATTERN = r"^postgres:17\.11-bookworm(?:@sha256:[0-9a-f]{64})?$"
SQL = Annotated[str, Field(min_length=1, max_length=16384)]
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})$")


class ContractError(ValueError):
    """Safe configuration/preflight error containing no supplied contents."""


def is_finite_json(value: object) -> bool:
    """Accept only JSON-shaped values, excluding Python's non-finite floats."""
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(is_finite_json(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and is_finite_json(item) for key, item in value.items())
    return False


def parse_timestamp(value: object) -> datetime:
    """Parse an explicit timezone-aware ISO timestamp, never epoch numbers."""
    if type(value) is str and _TIMESTAMP.fullmatch(value):
        value = datetime.fromisoformat(value.replace("z", "+00:00").replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("A timezone-aware ISO timestamp is required")
    try:
        value.astimezone(timezone.utc)
    except OverflowError:
        raise ValueError("Timestamp must be representable in UTC") from None
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, validate_default=True)


class Backup(StrictModel):
    path: Annotated[str, Field(min_length=1, max_length=4096)]
    sha256: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{64}$")]

    @field_validator("path")
    @classmethod
    def usable_path(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Archive path must be nonempty")
        return value


class Check(StrictModel):
    name: Annotated[str, Field(min_length=1, max_length=128, description="Unique identifier; lifecycle names, committed-write-ledger and the application- prefix are reserved.")]
    sql: SQL
    expected: JsonValue

    @field_validator("name", "sql")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value

    @field_validator("name")
    @classmethod
    def nonreserved_name(cls, value: str) -> str:
        if value.strip().casefold() in RESERVED_CHECK_NAMES or value.strip().casefold().startswith('application-'):
            raise ValueError("Check name is reserved for report metadata")
        return value

    @field_validator("expected", mode="before")
    @classmethod
    def json_expected(cls, value: object) -> object:
        if not is_finite_json(value):
            raise ValueError("Expected value must be finite JSON")
        return value


class Freshness(StrictModel):
    sql: SQL
    incident_at: datetime
    max_data_age_seconds: Annotated[int | float, Field(ge=0, le=86400)]

    @field_validator("sql")
    @classmethod
    def nonblank_sql(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("SQL must not be blank")
        return value

    @field_validator("incident_at", mode="before")
    @classmethod
    def aware_incident(cls, value: object) -> datetime:
        return parse_timestamp(value)


class LedgerSpec(Backup):
    sql: SQL

    @field_validator('sql')
    @classmethod
    def nonblank_sql(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Ledger SQL must not be blank')
        return value


class Contract(StrictModel):
    version: Literal[1]
    backup: Backup
    image: Annotated[str, Field(pattern=IMAGE_PATTERN)] = APPROVED_IMAGE
    checks: Annotated[list[Check], Field(min_length=1)]
    freshness: Freshness
    ledger: LedgerSpec | None = None
    application_journey: bool = False
    max_restore_seconds: Annotated[int | float, Field(gt=0, le=3600)] = 300

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value

    @model_validator(mode="after")
    def unique_names(self) -> Contract:
        names = [check.name for check in self.checks]
        if len(names) != len(set(names)):
            raise ValueError("Check names must be unique")
        return self


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON numbers are unsupported")


def _unique_contract_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate contract keys are ambiguous')
        result[key] = value
    return result


def load_contract(path: Path) -> Contract:
    """Load schema-validated JSON; archive verification is a separate phase."""
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(MAX_CONTRACT_BYTES + 1)
        if len(data) > MAX_CONTRACT_BYTES:
            raise ContractError("Contract exceeds the 128 KiB limit.")
        payload = json.loads(data.decode("utf-8"), parse_constant=_reject_constant,
                             object_pairs_hook=_unique_contract_object)
        if not is_finite_json(payload):
            raise ContractError("Contract must contain only finite JSON values.")
        return Contract.model_validate(payload)
    except ContractError:
        raise
    except OSError:
        raise ContractError("Contract could not be read.") from None
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise ContractError("Contract is invalid; check its schema, types and bounds.") from None


def resolve_archive(contract: Contract, contract_path: Path) -> Path:
    """Resolve backup.path against the contract's directory, never the cwd."""
    try:
        archive = Path(contract.backup.path)
        if not archive.is_absolute():
            archive = Path(contract_path).resolve().parent / archive
        return archive.resolve()
    except (OSError, RuntimeError, ValueError):
        raise ContractError("Archive path could not be resolved.") from None


def verify_archive(contract: Contract, contract_path: Path) -> Path:
    """Check existence, size, PGDMP magic and SHA-256; return the archive path."""
    archive = resolve_archive(contract, contract_path)
    try:
        if not archive.is_file():
            raise ContractError("Archive must be an existing regular file.")
        if archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ContractError("Archive exceeds the 64 MiB limit.")
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            prefix = stream.read(5)
            if prefix != b"PGDMP":
                raise ContractError("Archive is not PostgreSQL custom format.")
            digest.update(prefix)
            size = len(prefix)
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                if size > MAX_ARCHIVE_BYTES:
                    raise ContractError("Archive exceeds the 64 MiB limit.")
                digest.update(chunk)
        if digest.hexdigest() != contract.backup.sha256.lower():
            raise ContractError("Archive SHA-256 does not match the contract.")
        return archive
    except OSError:
        raise ContractError("Archive could not be read.") from None
