# v0.1 validation evidence

**77 tests passed: 71 unit/controlled-process tests and six real Docker/PostgreSQL integration tests.** There were zero failures, errors or skips in the recorded run. Validation completed on 6 October 2026 at 18:27:42 UTC (23:57:42 IST).

The [machine-readable record](../../evidence/local-validation.json) contains environment versions, image identity and SHA-256 hashes of the exact source, tests, dependency configuration, workflow and schema tested. The [test transcript](../../evidence/local-test-run.txt) lists each test. This is a local validation record; GitHub Actions and a second clean machine have **not** run it. Source fingerprints identify the tested files because this local repository has no commit yet. Documentation and evidence copies were finalized afterward.

## Observed integration outcomes

| Scenario | Result / CLI exit | What actually happened | Attempt / cleanup seconds |
|---|---|---|---|
| [Healthy](../../evidence/scenarios/healthy.json) | PASS / 0 | Snapshot equality, revision invariant and checkpoint policy passed | 4.015 / 0.719 |
| [Stale](../../evidence/scenarios/stale.json) | FAIL / 1 | Snapshot/invariant passed; checkpoint age 120 seconds exceeded the 60-second policy | 4.469 / 0.625 |
| [Inconsistent](../../evidence/scenarios/inconsistent.json) | FAIL / 1 | Snapshot equality passed, but a missing current-revision snapshot violated the independent business invariant | 4.797 / 0.625 |
| [Corrupt](../../evidence/scenarios/corrupt.json) | INCOMPLETE / 2 | Matching checksum and valid archive magic did not make a truncated archive restorable; failure occurred during restore | Incomplete / 0.687 |

These expected FAIL/INCOMPLETE outcomes are successful negative tests. Cleanup passed with no remaining owned resources for all four scenarios. A subsequent read-only Docker query for the RestoreProof run label returned no containers. See [residual-resource check](../../evidence/residual-resources.json).

Two further live integration checks verified:

- [Isolation and limits](../../evidence/isolation.json): network mode `none`, no published ports or host bind/volume mounts, 512 MiB memory, one CPU, 128 PIDs, and 256 MiB PostgreSQL tmpfs. The test inspected Docker's actual configuration, then cleaned the container.
- [Recovery cleanup](../../evidence/cleanup-recovery.json): a new adapter recovered an existing owned container using its run ID; repeating cleanup was also successful. This simulates discovering a leftover resource. It does **not** demonstrate killing a verifier process or losing the Docker daemon mid-restore.

Scenario JSON copies retain original checks, IDs, hashes, timestamps and timing values. Only the machine-specific `report_path` is replaced with a portable location. JUnit copies accompany each scenario. [Evidence provenance](../../evidence/provenance.json) records original and copied file hashes. Original reports and synthetic dump fixtures remain in the local, Git-ignored `runs/verified-local/` directory; dumps are excluded from the distributable archive.

## Measurement limits

The attempt timer begins before contract preflight and ends after database/checkpoint verification. It includes provisioning and restore, excludes demo source generation, and reports cleanup separately. The corrupt attempt did not finish verification; its total recorded lifecycle duration was 3.781 seconds. That number is not a successful recovery time.

These are single runs of a tiny synthetic fixture with a previously pulled image on one development computer. Hardware and competing-load controls were not recorded, so these are diagnostic timings, not performance benchmarks, production RTOs, incident MTTRs or comparative improvements. Checkpoint ages use a fixed synthetic logical clock. They do not measure production data loss or prove gap-free transaction recovery.

## Environment

| Component | Recorded value |
|---|---|
| Host | Windows 11, build 26300 |
| Python | 3.12.14 |
| Docker Desktop | 4.90.0 |
| Docker Engine | 29.7.2, API 1.55 |
| Container platform | Linux amd64, WSL2 kernel 6.18.33.2 |
| PostgreSQL reference | `postgres:17.11-bookworm` |
| Observed image digest | `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826` |

Docker initially failed on a stale runtime socket. With the user's authorization, its runtime directory was preserved under a timestamped backup name and Docker was restarted. The engine subsequently became healthy. No Docker data reset or image/volume deletion was performed. The runtime backup remains on the host. Test commands used a workspace-local Docker CLI configuration and the local Linux-engine named pipe.

## Reproduce

Install the project using the [README quickstart](../../README.md). Ensure the intended local Linux Docker engine is running and pull the approved image. From the project directory:

```powershell
$env:RESTOREPROOF_INTEGRATION = '1'
$env:RESTOREPROOF_EVIDENCE_DIR = 'runs/reproduction'
python -m unittest discover -s tests -v
```

```sh
RESTOREPROOF_INTEGRATION=1 RESTOREPROOF_EVIDENCE_DIR=runs/reproduction \
  python -m unittest discover -s tests -v
```

The recorded run used a small local wrapper around the same unittest discovery to capture counts, environment and fingerprints. The wrapper is not needed to run the tests. The integration suite uses the approved tag and records the observed image ID; compare that ID before claiming an identical-image reproduction. For a digest-specific demo:

```sh
python -m restoreproof demo --scenario healthy --output runs/pinned \
  --image postgres:17.11-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826
```

## Remaining gates

- Execute the configured Ubuntu CI workflow and reproduce from a clean checkout/environment.
- Interrupt real verifier processes and exercise daemon loss, then prove recovery and resource accounting.
- Compare recovered committed writes against an independent ledger, including gaps and duplicate/reordered writes.
- Boot an application against restored data and verify access controls plus an actual read/write journey.

The [acceptance checklist](acceptance.md) separates live evidence, controlled tests and pending exercises. v0.1 demonstrates database restore verification and selected application data invariants; it does not yet establish end-to-end application recovery.
