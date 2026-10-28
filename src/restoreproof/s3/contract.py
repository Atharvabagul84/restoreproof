"""Trusted backup identity; capture time is independent of upload time."""
from datetime import datetime
import json
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator

from ..chisel.contract import AppContract
from ..contract import (ContractError, StrictModel, MAX_CONTRACT_BYTES, parse_timestamp,
                        _reject_constant, _unique_contract_object)


class S3Backup(StrictModel):
    bucket: Annotated[str, Field(pattern=r'^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$')]
    key: Annotated[str, Field(min_length=1, max_length=1024)]
    version_id: Annotated[str, Field(min_length=1, max_length=1024)]
    sha256: Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
    expected_bucket_owner: Annotated[str, Field(pattern=r'^[0-9]{12}$')]
    captured_at: datetime
    max_age_seconds: Annotated[int, Field(ge=1, le=2592000)] = 86400

    @field_validator('key', 'version_id')
    @classmethod
    def bounded_identity(cls, value):
        if (not value.strip() or len(value.encode('utf-8')) > 1024
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            raise ValueError('Invalid object identity.')
        return value

    @field_validator('version_id')
    @classmethod
    def immutable_version(cls, value):
        if value.casefold() == 'null':
            raise ValueError('A versioned object is required.')
        return value

    @field_validator('captured_at', mode='before')
    @classmethod
    def explicit_timestamp(cls, value):
        return parse_timestamp(value)


class S3RecoveryContract(AppContract):
    backup: S3Backup


def load_contract(path):
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_CONTRACT_BYTES + 1)
        if len(data) > MAX_CONTRACT_BYTES:
            raise ValueError('Oversized contract.')
        payload = json.loads(data, parse_constant=_reject_constant, object_pairs_hook=_unique_contract_object)
        return S3RecoveryContract.model_validate(payload)
    except (OSError, ValueError, TypeError, RecursionError):
        raise ContractError('Invalid S3 recovery contract; check identity, timestamp and bounds.') from None
