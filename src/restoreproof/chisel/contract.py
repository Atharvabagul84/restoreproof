"""Fixed application identity and independent pre-backup recovery expectations."""
import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from ..contract import (Backup, ContractError, StrictModel, MAX_CONTRACT_BYTES,
                        _reject_constant, _unique_contract_object, is_finite_json)

SOURCE_COMMIT = 'fdb206cb24b3319328315eadaaee01eb03fda432'
UUID = Annotated[str, Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')]
SHA256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class AppContract(StrictModel):
    version: Literal[1]
    application: Literal['chisel']
    source_commit: Literal['fdb206cb24b3319328315eadaaee01eb03fda432']
    backup: Backup
    owner_id: UUID
    workspace_id: UUID
    outsider_workspace_id: UUID
    brief_id: UUID
    brief_sha256: SHA256
    max_recovery_seconds: Annotated[int | float, Field(gt=0, le=3600)] = 300

    @field_validator('version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Version must be an integer.')
        return value


def load_contract(path: Path) -> AppContract:
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(MAX_CONTRACT_BYTES + 1)
        if len(data) > MAX_CONTRACT_BYTES:
            raise ValueError('Contract exceeds size bound.')
        payload = json.loads(data, parse_constant=_reject_constant, object_pairs_hook=_unique_contract_object)
        if not is_finite_json(payload):
            raise ValueError('Non-finite contract.')
        return AppContract.model_validate(payload)
    except (OSError, ValueError, TypeError, RecursionError):
        raise ContractError('Invalid application contract; check schema, identity and bounds.') from None


def canonical_sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()
