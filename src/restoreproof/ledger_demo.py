"""Synthetic write acknowledgements recorded outside the backup target."""
import hashlib
import json
from pathlib import Path

LEDGER_SQL = """SELECT coalesce(json_agg(row_to_json(w) ORDER BY sequence), '[]'::json)
FROM (SELECT write_id, sequence,
    encode(sha256(convert_to(payload_text, 'UTF8')), 'hex') AS payload_sha256,
    to_char(acknowledged_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS acknowledged_at
    FROM app.acknowledged_writes) w"""


def prepare_ledger(source, folder: Path, scenario: str) -> dict:
    """Record each expected write only after its commit returns successfully.

    This small single-client lab uses fixed logical timestamps. The ledger is
    written by the client before fault injection/dump, never reconstructed from
    recovered data. Generated IDs, sequence and payloads are trusted constants.
    """
    source.execute('''CREATE TABLE app.acknowledged_writes (
        write_id text PRIMARY KEY, sequence bigint UNIQUE NOT NULL,
        payload_text text NOT NULL, acknowledged_at timestamptz NOT NULL);''')
    ledger = {'version': 1, 'writes': []}
    path = folder / 'acknowledged-writes.json'
    for sequence in (1, 2, 3):
        write_id = f'write-{sequence:03d}'
        payload = f'order-{sequence}:quantity={sequence}'
        timestamp = f'2026-01-01T00:00:0{sequence}Z'
        source.execute(f"INSERT INTO app.acknowledged_writes VALUES ('{write_id}', {sequence}, '{payload}', '{timestamp}');")
        ledger['writes'].append({'write_id': write_id, 'sequence': sequence,
                                 'payload_sha256': hashlib.sha256(payload.encode('utf-8')).hexdigest(),
                                 'acknowledged_at': timestamp})
        path.write_text(json.dumps(ledger, indent=2) + '\n', encoding='utf-8')
    if scenario == 'ledger-gap':
        source.execute("DELETE FROM app.acknowledged_writes WHERE write_id = 'write-002';")
    return {'path': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'sql': LEDGER_SQL}
