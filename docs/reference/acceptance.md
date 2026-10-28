# Acceptance checklist

For v0.4 exact-version retrieval, storage failures, real Chisel recovery and history, see [S3 acceptance and limits](../guides/s3-recovery.md) and [revision-specific validation](../history/validation-v04.md). [Real S3 with local Chisel passed](../history/validation-aws-live.md); GitHub-to-AWS OIDC and scheduled cloud recovery remain blocked. The checklist below preserves the earlier database/failure-drill milestone.

See the [failure-drill validation record](../history/validation-failure-drills.md) for the new milestone's final result. The [v0.2 validation](../history/validation-v02.md) and [v0.1 validation](validation.md) preserve earlier revision-specific results; their counts are not overwritten by later tests.

## Delivered behavior

- [x] Strict, bounded contracts and archive preflight; duplicate JSON keys cannot silently disable selected checks.
- [x] Real healthy, stale, inconsistent and corrupt-archive PostgreSQL restores, with distinct PASS/FAIL/INCOMPLETE semantics.
- [x] Real container inspection confirms no database network, published ports or bind/volume mounts, with bounded resource limits.
- [x] Recovery cleanup works through a fresh adapter and is repeatable.
- [x] External acknowledged-write ledger detects an interior missing write while the latest checkpoint still passes.
- [x] Ledger validation covers missing/extra/duplicate writes, content and metadata mismatches, invalid evidence and finite report limits.
- [x] Real HTTP application reads an existing restored order, writes a new order and reads it on a separate request.
- [x] Real restricted PostgreSQL login cannot create tables or bypass row security; HTTP tenant isolation and unauthenticated denial are checked.
- [x] Database checks can pass while the application fails to recover a required order or cannot perform a write.
- [x] Application bootstrap does not reconstruct missing tables, policies or seed data. Partial successful journey evidence cannot become PASS.
- [x] Hard-killed verifier journals stay INCOMPLETE; recovery removes only owned targets and preserves another live container.
- [x] A tagged query is observed actively executing in PostgreSQL before its verifier is terminated.
- [x] Two overlapping verifiers share an output directory without run-ID collisions or cross-cleanup.
- [x] The earlier v0.2 revision passed 134 local tests, including 18 real integration tests, and its expanded suite passed on hosted Ubuntu. Repository visibility remains private.
- [x] Local active-COPY drills observe `pg_restore` processing rows before killing the verifier tree or terminating the COPY backend.
- [x] Hard verifier termination retains an INCOMPLETE journal and supports ownership-scoped recovery; backend termination produces exit 2, restore-phase error, no downstream checks, and automatic cleanup.
- [x] Each active-COPY drill preserves an unrelated test container and completes a healthy retry using the same archive.

## Current milestone status

All three jobs in the successful Ubuntu run (pre-release CI run 37517902305) passed for implementation `a87739c19e73c9ca08c78aced535da4a0f8453e8`: **151 distinct tests, including 21 live integration tests**.

| Job | Observed result | Distinct coverage |
|---|---|---|
| Unit/guards | 151 discovered: 130 passed, 21 opt-in tests skipped | 130 unit/guard tests |
| Normal Docker | 23 passed | 20 live integration tests plus three repeated guards |
| Private daemon | 12 passed | One live integration test plus 11 repeated guards |

Repeated guards are counted once in the 151-test total. Local default discovery also passed 130 unit/guard tests with 21 skips; the corrected paired COPY tests passed locally in 48.107 seconds. Local skips are not local integration passes.

- [x] All 20 normal-Docker integration tests passed on hosted Ubuntu at this revision.
- [x] The private daemon stopped gracefully with exit 0. Verification and attempted cleanup remained INCOMPLETE during the outage.
- [x] After the private daemon restarted, the retained target was exited; ownership-scoped cleanup and repeated absence checks passed, with the failed journal unchanged.
- [x] The original runner daemon and its running sentinel were unchanged; final drill cleanup passed.

The [validation record](../history/validation-failure-drills.md) links the retained evidence and records earlier harness failures separately from this successful revision.

## Limits of this acceptance

The contract, lifecycle, report-write, process-timeout, changed-archive and malformed-data tests also include controlled/fake external boundaries. Live integration supplements those tests; it does not turn every injected failure into a demonstrated infrastructure fault.

The original restore-phase checkpoint occurs after `pg_restore` finishes; the active-query case interrupts a real sleeping read. The newer COPY cases require server-side progress with processed rows and an active COPY command before interruption. Those rows are uncommitted within the restore transaction. The fixture gate and bounded cleanup/control-response barrier are test instrumentation; real control responses and a healthy same-archive retry remain required. See [interruption boundaries](interruption-drill.md) and [failure-drill design](failure-drills.md).

The private-daemon experiment uses graceful `SIGTERM` with `live-restore=false`, on a disposable Linux runner. Its own containers may stop. It does not restart Docker Desktop, stop the runner's original daemon, simulate abrupt power loss, or prove data-plane continuity. Later cleanup must remain separate evidence and must not rewrite the failed verification as PASS.

## Future work

- [ ] Exercise abrupt daemon crashes and live-restore data-plane continuity as separate fault models.
- [ ] Restore a continuously written dataset using a well-defined exported snapshot/WAL boundary.
- [ ] Add an application-specific adapter for an existing project, including real identity-provider and external-service dependencies.
- [ ] Account for ambiguous client acknowledgements and prove ledger coverage under client failure.
- [ ] Run repeated workload benchmarks with documented data volume, hardware and cache state.

The included order service and write generator are synthetic lab fixtures. Passing this checklist does not establish production readiness, recovery of a whole hosted system, or a production RPO/RTO.
