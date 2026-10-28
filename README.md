# RestoreProof

[![Validate](https://github.com/Atharvabagul84/restoreproof/actions/workflows/validate.yml/badge.svg)](https://github.com/Atharvabagul84/restoreproof/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)
![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-336791.svg)

**Row counts aren't recovery.** A PostgreSQL restore can finish cleanly and still break the application: a business invariant is violated, the data is older than your recovery objective, or acknowledged writes are missing.

RestoreProof restores a backup into a disposable, network-isolated container, then proves the *application* recovered: business invariants, data freshness, a real read/write journey through the app, and exact accounting of lost writes. Every run leaves JSON, JUnit and HTML evidence.

It builds on PostgreSQL's own `pg_restore`. It is not a backup engine.

## How it compares

| Check | `pg_restore` exit code | Databasus / pg-backup-verify | BackupDrill | AWS Backup restore testing | **RestoreProof** |
|---|:-:|:-:|:-:|:-:|:-:|
| Restore into a disposable target | — | ✓ | ✓ | ✓ | ✓ |
| Archive checksum before restore | — | — | ✓ | — | ✓ |
| Table / row-count comparison | — | ✓ | non-empty tables | — | ✓ |
| Custom SQL checks | — | — | via custom command | via your own Lambda | ✓ declarative |
| Business invariants and freshness (RPO) policy | — | — | — | — | ✓ |
| Application journey through HTTP (read, write, tenant isolation) | — | — | — | — | ✓ |
| External write ledger (exactly which writes were lost) | — | — | — | — | ✓ |
| Evidence journal (JSON + JUnit + offline HTML) | — | report | — | job status | ✓ |
| Runs fully offline, no cloud account | ✓ | ✓ | Supabase only | AWS only | ✓ |

*"—" means not documented. Based on each project's public documentation as of 2026-10-25: [Databasus](https://github.com/databasus/databasus), [pg-backup-verify](https://github.com/pACCOU/pg-backup-verify), [BackupDrill](https://www.postgresql.org/about/news/backupdrill-open-source-supabase-postgres-backups-with-automated-restore-drills-3413/), [AWS Backup restore testing](https://docs.aws.amazon.com/aws-backup/latest/devguide/restore-testing.html). Corrections welcome.*

## How it works

```mermaid
flowchart LR
  A[Trusted contract + custom archive] --> B[Schema / size / hash preflight]
  B --> C[Owned disposable PostgreSQL target]
  C --> D[Copied-archive hash check + pg_restore]
  D --> E[Snapshot / business / freshness checks]
  E --> H[Optional external write ledger]
  H --> I[Optional HTTP application journey]
  I --> F[Ownership-checked cleanup]
  F --> G[JSON journal + JUnit]
```

The PostgreSQL target runs with `--network none`, all capabilities dropped except the four its entrypoint needs (`CHOWN`, `FOWNER`, `SETGID`, `SETUID`), `no-new-privileges`, CPU/memory/process limits, tmpfs data storage and no published ports. Its root filesystem stays writable because the archive is copied in with `docker cp`. Application containers in the Chisel journey also run read-only with every capability dropped. Cleanup only removes containers RestoreProof can prove it owns, and a cleanup failure overrides an otherwise green result.

## Quickstart

Requires Python 3.11+ and Docker with a local Linux container engine. No cloud account or API key is needed.

```sh
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt .
docker pull postgres:17.11-bookworm
python -m restoreproof demo --scenario healthy --output runs/healthy
python -m restoreproof app-demo --scenario all --output runs/chisel   # full application recovery
```

On Windows, enable long paths before cloning: `git config --global core.longpaths true`.

## What the scenarios show

| Scenario | What happens | Result |
|---|---|---|
| `healthy` | Snapshot, revision and freshness checks pass | `PASS` (0) |
| `stale` | Data restores correctly but is older than the policy allows | `FAIL` (1) |
| `inconsistent` | The backup faithfully restores an already broken source; a business invariant catches it | `FAIL` (1) |
| `corrupt` | A truncated archive keeps its magic bytes and checksum, but PostgreSQL can't restore it | `INCOMPLETE` (2) |
| `application` | The restored order is read through HTTP, a new order is written and read back, cross-tenant access is denied | `PASS` (0) |
| `application-broken` | Database checks pass, but the application can't find a required record | `FAIL` (1) |
| `ledger-gap` | The latest checkpoint passes, but the external ledger shows `write-002` was lost | `FAIL` (1) |
| `app-demo` | Recovers [Chisel](docs/guides/chisel-recovery.md) (Next.js + Supabase Auth) end to end, plus four controlled failures | `PASS` / `FAIL` |

Run each with `python -m restoreproof demo --scenario <name> --output runs/<name>`. Failure scenarios exit non-zero by design. Exit codes: `PASS` 0, `FAIL` 1, `INCOMPLETE` 2, `INVALID` 3 ([details](docs/guides/usage.md#outcome-contract)).

## Verify your own backup

Write a contract that names your custom-format dump, its SHA-256 and SQL checks that each return one JSON value:

```sh
python -m restoreproof verify path/to/contract.json --output runs/custom
```

See the [usage reference](docs/guides/usage.md) for the contract format, ledger and application journey options, cleanup after interruption, and tests. Contracts and archives must be trusted: this is not a sandbox for hostile dumps.

## Features

- **Application-level recovery:** separates "the database started" from "the application recovered", with freshness (RPO) and duration objectives evaluated per run.
- **Failure drills:** kill the verifier mid-restore, terminate the PostgreSQL backend, and stop the Docker daemon, then prove owned cleanup and a healthy retry ([failure drills](docs/reference/failure-drills.md)).
- **S3 backup sources:** pinned object versions with checksum and age checks; Terraform for private, encrypted, versioned storage ([S3 recovery](docs/guides/s3-recovery.md)).
- **Tested and cost-safe CI:** 245 tests (the Docker integration suites run in CI), actions pinned to commits, hosted jobs gated on verified free usage, sanitized retained evidence.

## Documentation

Start at the [documentation index](docs/README.md): [usage](docs/guides/usage.md) · [architecture](docs/ARCHITECTURE.md) · [limitations](docs/reference/limitations.md) · [offline HTML report](docs/guides/offline-report.md) · [cost policy](docs/reference/cost-policy.md) · [design decisions](docs/decisions/) · [pre-release history](docs/history/release-history.md).

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, checks and the pull-request flow, and [SECURITY.md](SECURITY.md) for the threat model and how to report a vulnerability. Changes are listed in the [changelog](CHANGELOG.md).

## Limitations

Lab-scale by design: archives up to 64 MiB, one CPU and 512 MiB memory per target. The application journey is fixed to the bundled fixtures (no arbitrary-app plugin yet). Lab timings are not production MTTR or RPO measurements. See [limitations](docs/reference/limitations.md).

## License

[MIT](LICENSE) © 2026 Atharva Bagul
