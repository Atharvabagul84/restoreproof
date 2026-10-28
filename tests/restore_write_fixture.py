"""A small trusted archive whose COPY operation has an observable bounded gate.

PostgreSQL 17 references:
https://www.postgresql.org/docs/17/sql-copy.html (CHECK constraints run during COPY)
https://www.postgresql.org/docs/17/app-pgrestore.html (validated CHECK is pre-data)
https://www.postgresql.org/docs/17/progress-reporting.html#COPY-PROGRESS-REPORTING
https://www.postgresql.org/docs/17/functions-admin.html#FUNCTIONS-ADVISORY-LOCKS

The VOLATILE CHECK and seed-session switch are test instrumentation, not a
recommended production data constraint. No RestoreProof implementation hook is used.
"""

import hashlib
import json
import uuid

from restoreproof.contract import APPROVED_IMAGE
from restoreproof.docker_postgres import DockerPostgres

ROW_COUNT = 2048
GATE_ROW = 1536
MAX_FIXTURE_BYTES = 1024 * 1024
SUMMARY_SQL = """SELECT json_build_object(
    'rows', count(*), 'min_id', min(id), 'max_id', max(id),
    'bad_payloads', count(*) FILTER (WHERE payload <> md5(id::text)))
    FROM drill.restore_rows"""
EXPECTED = {"rows": ROW_COUNT, "min_id": 1, "max_id": ROW_COUNT, "bad_payloads": 0}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def build_fixture(root):
    root.mkdir(parents=True, exist_ok=True)
    lock_key = uuid.uuid4().int % (2**31 - 1) + 1
    sql = f"""
    SET restoreproof.seed_mode = 'on';
    CREATE SCHEMA drill;
    CREATE FUNCTION drill.copy_gate(row_id integer) RETURNS boolean
    LANGUAGE plpgsql VOLATILE AS $gate$
    DECLARE deadline timestamptz;
    BEGIN
      IF row_id = {GATE_ROW}
         AND coalesce(current_setting('restoreproof.seed_mode', true), '') <> 'on' THEN
        deadline := clock_timestamp() + interval '25 seconds';
        LOOP
          IF NOT pg_try_advisory_lock({lock_key}::bigint) THEN
            RETURN true;
          END IF;
          PERFORM pg_advisory_unlock({lock_key}::bigint);
          IF clock_timestamp() >= deadline THEN
            RAISE EXCEPTION 'Test COPY gate was not acknowledged within 25 seconds';
          END IF;
          PERFORM pg_sleep(0.05);
        END LOOP;
      END IF;
      RETURN true;
    END
    $gate$;
    CREATE TABLE drill.restore_rows (
      id integer PRIMARY KEY,
      payload text NOT NULL,
      committed_at timestamptz NOT NULL,
      CONSTRAINT observe_copy CHECK (drill.copy_gate(id))
    );
    INSERT INTO drill.restore_rows
      SELECT n, md5(n::text), '2026-01-01T00:00:00Z'::timestamptz
      FROM generate_series(1, {ROW_COUNT}) n ORDER BY n;
    """
    (root / "fixture.sql").write_text(sql, encoding="utf-8")
    run_id = uuid.uuid4().hex
    journal = {"source_run_id": run_id, "status": "INCOMPLETE", "lock_key": lock_key,
               "rows": ROW_COUNT, "gate_row": GATE_ROW}
    write_json(root / "source.json", journal)
    source = DockerPostgres(APPROVED_IMAGE, run_id, timeout_seconds=45)
    try:
        journal["target"] = source.create()
        write_json(root / "source.json", journal)
        source.execute(sql)
        observed = source.query(SUMMARY_SQL)
        if observed != EXPECTED:
            raise AssertionError(f"Synthetic source does not match independent expectations: {observed}")
        write_json(root / "expected.json", EXPECTED)
        archive = root / "backup.dump"
        source.dump(archive)
        if archive.stat().st_size >= MAX_FIXTURE_BYTES:
            raise AssertionError("Restore-write fixture must remain smaller than 1 MiB")
        contract = {
            "version": 1, "image": APPROVED_IMAGE,
            "backup": {"path": archive.name, "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()},
            "checks": [{"name": "restored-rows", "sql": SUMMARY_SQL, "expected": EXPECTED}],
            "freshness": {
                "sql": "SELECT to_json(to_char(max(committed_at) AT TIME ZONE 'UTC', "
                       "'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"')) FROM drill.restore_rows",
                "incident_at": "2026-01-01T00:00:30Z", "max_data_age_seconds": 60,
            },
            "max_restore_seconds": 90,
        }
        write_json(root / "contract.json", contract)
        journal.update(status="PASS", archive_bytes=archive.stat().st_size,
                       archive_sha256=contract["backup"]["sha256"])
    finally:
        journal["cleanup"] = source.cleanup()
        if journal["cleanup"]["status"] != "PASS":
            journal["status"] = "INCOMPLETE"
        write_json(root / "source.json", journal)
        if journal["cleanup"]["status"] != "PASS":
            raise RuntimeError(f"Source fixture cleanup incomplete: {journal['cleanup']}")
    return root / "contract.json", lock_key
