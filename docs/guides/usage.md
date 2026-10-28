# Usage reference

Detailed CLI behaviour, contract rules, outcome codes, cleanup, tests and failure drills. Moved here from the README on 2026-10-25 without changes to the guarantees described.

## Demo output layout

The CLI prints a JSON summary with `status`, `run_id`, `report_path`, `contract_path` and cleanup status. Each verification writes its own directory:

```text
runs/healthy/
  fixture-<source-run-id>/
    source.json
    snapshot-manifest.json
    backup.dump
    contract.json
  <verification-run-id>/
    report.json
    junit.xml
```

Source and target containers are separately named and labeled; both are cleaned after their use. No ports are published and no host directories are mounted. Database storage uses bounded tmpfs. The Docker context must point to your intended local engine; this version does not discover or authorize remote environments.

## Synthetic clock

The demo uses a fixed **synthetic logical clock**. Its checkpoint age is a controlled policy example, not a measured production RPO. The data remains quiescent between capturing snapshot expectations and creating the backup. Backup-snapshot correctness and data freshness are separate checks.

## Prove the difference between database and application recovery

```sh
python -m restoreproof demo --scenario application --output runs/application
python -m restoreproof demo --scenario application-broken --output runs/application-broken
python -m restoreproof demo --scenario ledger-healthy --output runs/ledger-healthy
python -m restoreproof demo --scenario ledger-gap --output runs/ledger-gap
```

| Scenario | Expected outcome | What the reviewer sees |
|---|---|---|
| `application` | PASS / 0 | Restored order read through HTTP, new order written and read back, unauthorized and cross-tenant access denied |
| `application-broken` | FAIL / 1 | Baseline database checks pass, but the application cannot find its required existing order |
| `ledger-healthy` | PASS / 0 | Every known acknowledged write matches recovered identity, sequence, payload digest and timestamp |
| `ledger-gap` | FAIL / 1 | Latest checkpoint passes, but the external ledger identifies missing `write-002` |

The order API is a loopback-only, short-lived synthetic test application. Its bearer tokens are generated per run and are not stored in reports. PostgreSQL stays on `--network none`; database operations travel through Docker exec. It is not a deployable public HTTP service. The required order records and tenant policies must already exist in the backup; the journey does not recreate them.

The ledger demo records expected writes outside PostgreSQL only after each successful commit returns, before fault injection and backup. Recovered payload digests are recomputed from recovered UTF-8 payloads. A closed, quiescent write set makes exact missing-write accounting possible; this does not establish general production RPO. See the [ledger contract and limits](../reference/ledger.md).

For your own trusted contract, set `application_journey: true` to run this specific order fixture's journey, or add a `ledger` object with `path`, `sha256`, and a SQL query returning the recovered write array. Both are optional. A ledger path resolves against the contract directory; malformed or changed ledger files are rejected before allocation. The JSON schema documents these fields. The application journey is currently fixed to the included order schema, not an arbitrary-URL plugin.

## Verify your own trusted contract

Use a small custom-format dump and queries against that dump's schema. SQL must return **exactly one JSON value**. For example, use `to_json(count(*))`, `to_json(boolean_expression)` or `json_build_object(...)`, rather than unencoded text output.

```sh
python -m restoreproof verify path/to/contract.json --output runs/custom
```

The demo generates a complete runnable contract. A minimal illustrative contract looks like this; replace its path, digest, query and incident timestamp with real values:

```json
{
  "version": 1,
  "image": "postgres:17.11-bookworm",
  "backup": {"path": "backup.dump", "sha256": "<64-character SHA-256>"},
  "checks": [
    {"name": "required-features", "sql": "SELECT to_json(count(*)) FROM app.features", "expected": 2}
  ],
  "freshness": {
    "sql": "SELECT to_json(max(committed_at)) FROM app.checkpoints",
    "incident_at": "2026-01-01T00:00:30Z",
    "max_data_age_seconds": 60
  },
  "max_restore_seconds": 300
}
```

Contract paths resolve relative to the contract file. Unknown fields, non-finite values, empty checks, invalid timestamps, unsupported images and incorrect archive checksums fail before allocation. [JSON schema](../../schemas/contract-v1.json) describes structural rules; runtime validation also enforces archive size, unique names and reserved identifiers.

The approved image is `postgres:17.11-bookworm`, optionally followed by `@sha256:<digest>`. Tags can move: record the observed image ID from the report, and use a verified digest for stricter reproduction. Archives are limited to 64 MiB; the target has 512 MiB memory, one CPU and 256 MiB database tmpfs. This is intentionally a small lab workload.

Verification queries run in read-only transactions. **Contracts, archives and images must be trusted:** this is not a hostile-SQL or hostile-dump sandbox. PostgreSQL dumps can execute database code. Verification does not accept an existing target URL or restore into a production database.

## Outcome contract

| Status | Exit | Meaning |
|---|---:|---|
| `PASS` | 0 | All required checks completed successfully and owned cleanup was verified |
| `FAIL` | 1 | Completed verification disproved an application/freshness/duration expectation; cleanup succeeded |
| `INCOMPLETE` | 2 | Restore, query, interruption, evidence writing or cleanup could not be completed reliably |
| `INVALID` | 3 | Contract/archive preflight or explicit run/image input is invalid |

CLI syntax errors use argparse's standard exit 2. A `pg_restore` failure is incomplete verification; this version does not guess whether arbitrary stderr indicates corruption, permissions or another operational failure. Unknown or future checkpoint timestamps cannot become a green result. Cleanup failure overrides otherwise successful checks.

The measured verification attempt starts before contract preflight and ends after the selected data, checkpoint, ledger and application checks. It includes target provisioning and restore; cleanup time is separate. The recovery-duration objective is evaluated after the attempt, not a single global process deadline. Individual commands and readiness have bounded timeouts. A failed attempt's duration is not a successful recovery time, and a lab run is not incident MTTR.

## Cleanup after an interrupted process

```sh
python -m restoreproof cleanup <32-character-run-id>
```

Use the verification `run_id` from `report.json`, or `source_run_id` from a demo's `source.json`. Cleanup checks the exact name, run label and observed container ID. It never runs Docker prune. A renamed or ambiguous owned container is reported incomplete for inspection rather than deleted. Label checks assume a trusted Docker daemon; labels are not protection from a malicious Docker administrator.

JSON is the authoritative journal. Each evidence file is atomically replaced, and successful JSON is published after JUnit. They are not a filesystem transaction across two files; inspect JSON and process exit status if evidence writing fails.

## Test and CI

Fast contract, evaluation, lifecycle, CLI, reporting and subprocess tests:

```sh
python -m unittest discover -s tests -v
```

The PostgreSQL, HTTP journey, ledger, isolation, interruption and concurrency integration tests skip unless explicitly enabled:

```sh
# Linux/macOS
RESTOREPROOF_INTEGRATION=1 RESTOREPROOF_EVIDENCE_DIR=runs/integration python -m unittest discover -s tests -p 'test*integration.py' -v
```

```powershell
# Windows PowerShell
$env:RESTOREPROOF_INTEGRATION = '1'
$env:RESTOREPROOF_EVIDENCE_DIR = 'runs/integration'
python -m unittest discover -s tests -p 'test*integration.py' -v
```

The [GitHub Actions workflow](../../.github/workflows/validate.yml) defines unit/guard checks, normal Docker integration, a private-daemon drill and real Chisel recovery. Hosted execution requires the cost-policy gate `RESTOREPROOF_FREE_CI_VERIFIED=true`; all integration jobs depend on the gated unit job. Until account-level free allowances and spending controls are verified, run the documented tests locally. Skipped hosted jobs are not test passes. The daemon job uses `RESTOREPROOF_DAEMON_INTEGRATION=1`; normal Docker opt-in does not enable it. Curated JSON/JUnit evidence and diagnostic logs are retained even on failure. Actions are pinned to inspected commits. No cloud credentials or deployment permission are required. New test artifacts expire after one day; selected reviewed results remain in the repository. See the [cost policy](../reference/cost-policy.md).

## What the failure drills establish

Two tests observe real `pg_restore` COPY progress before injecting failure: one kills the verifier tree, while the other terminates the observed PostgreSQL backend and leaves the verifier to handle the error. Each requires owned cleanup, unrelated-container survival, and a healthy retry of the **same archive**. COPY rows are still inside an uncommitted restore transaction; this is not a committed-data-loss measurement.

The separate Linux drill uses a private Docker daemon and containerd. Controlled `SIGTERM` with `live-restore=false` made its Docker API unavailable; verification and cleanup remained INCOMPLETE. After restart, the retained target was exited, and ownership-scoped cleanup and repeated absence checks passed without rewriting the failed journal. The original daemon and sentinel were unchanged. This does not establish power-loss recovery or uninterrupted container operation, and it does not restart the user's Docker Desktop. See [failure-drill design](../reference/failure-drills.md) and [validated results](../history/validation-failure-drills.md).
