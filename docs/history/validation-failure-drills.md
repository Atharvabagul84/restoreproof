# Failure-drill validation

This milestone extends RestoreProof v0.2 with interrupted COPY writes and a controlled outage of a separate Docker daemon. The runtime package remains version 0.2.0: these additions exercise existing recovery behavior without changing the verifier implementation. The [repository](https://github.com/Atharvabagul84/restoreproof) remains private.

## Hosted result

On **7 October 2026 (IST)**, all three hosted jobs passed (pre-release CI run 37517902305) for implementation revision `a87739c19e73c9ca08c78aced535da4a0f8453e8`. Together they cover **151 distinct passing tests: 130 unit/guard tests and 21 live integration tests**.

| Job | Recorded result | What contributes to the distinct total |
|---|---|---|
| Unit | 151 discovered; 130 passed, 21 opt-in integrations skipped | 130 unit/guard tests |
| PostgreSQL | 23 passed in 106.890 seconds | 20 live Docker tests; three guards repeat from the unit job |
| Isolated daemon | 12 passed in 39.301 seconds | One real Linux daemon-outage test; 11 guards repeat from the unit job |

The [CI record](../../evidence/failure-drills/ci-validation.json) identifies the run, jobs, private visibility and retained artifacts. The [source provenance](../../evidence/failure-drills/provenance.json) records SHA-256 fingerprints of the tested Git blobs. Subsequent documentation/evidence-only commits do not change that implementation. Test durations describe suite execution, not service recovery objectives.

Local Windows discovery separately passed 130 tests with 21 integrations skipped in 5.246 seconds; the corrected two live COPY drills passed in 48.107 seconds. The [local transcript](../../evidence/failure-drills/local-unit-tests.log) and [post-run container inspection](../../evidence/failure-drills/local-residual-resources.json) are retained. No verifier, resilience-fixture or restore-write-fixture containers remained. The Linux-only daemon drill was executed on the hosted runner.

## What the tests require

| Fault | Evidence required for the test to pass |
|---|---|
| Kill the verifier during COPY | PostgreSQL reports an active COPY FROM with processed rows; hard termination leaves the saved journal INCOMPLETE; fresh ownership-scoped cleanup and repeated cleanup pass |
| Terminate the COPY backend | PostgreSQL confirms termination while the verifier remains alive; the verifier records a restore-phase failure, no downstream checks, exit 2, and successful owned cleanup |
| Healthy control for each COPY fault | A fresh run restores the same archive hash into a different container, observes COPY again, completes all checks and cleanup, and preserves the failed run's evidence |
| Stop the private daemon | Real restore reaches a test checkpoint; only the owned daemon receives SIGTERM; its Docker API becomes unavailable; verification and attempted cleanup stay INCOMPLETE |
| Restart and recover | The same private Docker state and target ID are found; ownership-scoped cleanup and repeated absence checks pass; the failed journal remains unchanged |
| Protect unrelated workloads | The unrelated fixture remains running through recovery; the original runner daemon identity and its sentinel start time remain unchanged |

Both hosted COPY faults observed **1,000 processed rows out of 2,048**, with `pg_restore`, active COPY FROM and PIPE recorded by PostgreSQL. The [hard-kill record](../../evidence/failure-drills/hosted-restore/2d66ed04318344759a9667f9dd1a92e6/restore-write-interruption.json) preserves the INCOMPLETE journal, successful repeated cleanup and passing same-archive retry. The [backend-termination record](../../evidence/failure-drills/hosted-restore/21e16ff87c3c4fe0a7eecdfda7044c2a/restore-backend-termination.json) includes PostgreSQL's true termination response, control-command exit 0, verifier exit 2, automatic cleanup and a passing retry.

The [daemon-outage record](../../evidence/failure-drills/hosted-daemon/17fd7ef8c5a24ef281a6061357e8c547/daemon-loss.json) records a graceful stop with exit 0, unavailable-API INCOMPLETE evidence, and an exited target found after restart. Recovery and repeated cleanup passed; the original daemon identity and running sentinel were preserved. [Isolation metadata](../../evidence/failure-drills/hosted-daemon/17fd7ef8c5a24ef281a6061357e8c547/isolation.json) includes private paths, owned process identities, Docker 28.0.4, containerd v2.3.6, VFS/cgroup configuration, and matching source/private image IDs. [Final cleanup](../../evidence/failure-drills/hosted-daemon/17fd7ef8c5a24ef281a6061357e8c547/test-cleanup.json) passed without errors.

Selected JSON/JUnit, test transcripts, observed environment and hash provenance are retained under `evidence/failure-drills`; the [evidence index](../../evidence/failure-drills/evidence-index.json) identifies their origins and hashes. Raw dumps and private daemon storage are excluded. Original path strings in reports describe their execution environment; retained copies use portable relative paths. CI artifacts expire after 14 days, while committed evidence remains available with the repository.

## What the first hosted attempt caught

The first run (pre-release CI run 37516631635) passed the earlier 18 Docker tests but exposed two harness assumptions. Docker 28 auto-selected the runner's system containerd endpoint even with private Docker directories; the isolation gate refused to proceed before loading an image or starting a private target. The corrected design explicitly owns a separate containerd process and passes its socket to Docker.

On the faster Linux runner, the verifier removed its target while the test's control SQL connection was still returning its response. That killed the observer with exit 137 and correctly failed both new tests. The correction coordinates only the test's cleanup timing: it requires the real control response before releasing the verifier's normal cleanup. It neither treats exit 137 as success nor weakens the PostgreSQL termination assertion.

## Boundaries

COPY progress is uncommitted work within a single restore transaction, not durable recovered data. The small fixture uses a bounded test-only CHECK/advisory-lock gate, with a same-archive healthy control. No production RPO, RTO, MTTR or throughput improvement is inferred from these runs.

The daemon experiment uses graceful SIGTERM with live restore disabled. Its containers may stop. It demonstrates unavailable Docker API handling and later cleanup, not abrupt power loss, uninterrupted workloads, or physical/WAL recovery. The Linux job starts its own daemon and container runtime; it does not stop the user's Docker Desktop or the runner's system services. Private runtime directories remain for the ephemeral runner's disposal, outside uploaded evidence.

See [drill design and reproduction](../reference/failure-drills.md) and [acceptance](../reference/acceptance.md). Earlier [v0.2 validation](validation-v02.md) remains revision-specific historical evidence.
