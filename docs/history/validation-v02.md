# v0.2 validation

This record covers the application journey, independent acknowledgement ledger, and interruption/concurrency changes. The private repository is [Atharvabagul84/restoreproof](https://github.com/Atharvabagul84/restoreproof).

## Local execution

On **7 October 2026 (IST)**, all **134 tests passed**, including **18 real Docker integration tests**, with zero failures, errors or skips. The combined run took 204.010 seconds on Windows with Docker Desktop's Linux engine. Separate post-run queries found neither verifier containers nor interruption-test fixture containers remaining.

The [machine-readable validation record](../../evidence/v02/local-validation.json) identifies the exact source/test/configuration fingerprints, environment, suite counts, image digest and residual-resource check. The [test transcript](../../evidence/v02/local-test-run.txt) records individual outcomes. Documentation and selected evidence copies are finalized after the suite runs; source fingerprints bind the tested implementation independently of that documentation commit.

## Hosted reproduction

The expanded v0.2 run (pre-release CI run 37514412501) **passed both jobs**, including all 18 real integration tests on Ubuntu, for implementation commit `051a45cd029dde71f272b65adde3c793f7cd5352`. The integration suite took 83.982 seconds in the hosted log. A retained artifact contains the synthetic recovery evidence and drill diagnostics. Subsequent documentation/evidence-only changes do not change that tested implementation.

The v0.1 baseline workflow (pre-release CI run 37512591480) passed both unit and PostgreSQL jobs on Ubuntu. Its evidence artifact was retained. v0.2's expanded workflow runs all files matching test*integration.py, including actual HTTP, ledger and hard-kill exercises. The [hosted validation record](../../evidence/v02/ci-validation.json) records the current run, commit and conclusion; a baseline success is not a claim about later changes.

## Evidence and boundaries

The [scenario index](../../evidence/v02/scenario-index.json) links selected portable JSON/JUnit copies and records hashes of their original local reports. Original synthetic dumps and detailed run journals remain under the local Git-ignored runs/v02/ directory and are not included in the distributable archive.

| Area | Required observation |
|---|---|
| Healthy database | Expected data, invariant, freshness and cleanup pass |
| Stale/inconsistent/corrupt database | Expected negative outcome with owned cleanup; corrupt archive remains INCOMPLETE |
| Application | All eight mandatory HTTP/security checks pass after restore |
| Broken application | Baseline SQL passes; missing restored order causes HTTP journey failure |
| Restricted identity | Actual session is the application role; RLS bypass and DDL attempts fail |
| Complete ledger | Three expected, recovered and matching writes |
| Interior gap | Three expected, two recovered/matching; only write-002 is missing; freshness still passes |
| Hard termination | Journal stays INCOMPLETE; fresh-adapter cleanup/repeat passes; unrelated target survives |
| Active query | Server-side pg_stat_activity proves tagged query is actively waiting in PgSleep before kill |
| Overlap | Distinct run IDs and containers; first cleanup preserves the second; both finish PASS |

Role grants are deliberately part of application bootstrap, while data/schema/policies come from the backup. The write ledger is recorded outside the source database after each successful client write, then sealed before fault injection. Neither mechanism asserts recovery of a production application's whole dependency graph.

Negative scenario FAIL/INCOMPLETE results are successful tests when they match the expected failure. An interrupted journal is never rewritten to PASS merely because cleanup later succeeds.

The fixture uses fixed logical timestamps, bounded data and a cached image. No production RPO, business MTTR, percentage improvement or workload benchmark is claimed. See [ledger limits](../reference/ledger.md), [interruption boundaries](../reference/interruption-drill.md) and [scope](../reference/limitations.md).

## Reproduction

Follow the [quickstart](../../README.md), then enable the complete suite:

```powershell
$env:RESTOREPROOF_INTEGRATION = '1'
$env:RESTOREPROOF_EVIDENCE_DIR = 'runs/reproduction'
python -m unittest discover -s tests -v
```

```sh
RESTOREPROOF_INTEGRATION=1 RESTOREPROOF_EVIDENCE_DIR=runs/reproduction \
  python -m unittest discover -s tests -v
```

Use a short evidence directory on Windows to avoid path-length limitations. Compare recorded image IDs and source fingerprints before describing a reproduction as identical. The workflow retains JSON, JUnit and diagnostic logs for 14 days; selected results stored in the repository are longer-lived snapshots.
