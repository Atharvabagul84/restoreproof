# Interruption and concurrency drill boundaries

The project now separates phase/query interruption, active restore COPY interruption, and a private-daemon outage. Their evidence must not be treated as interchangeable. See [failure-drill design](failure-drills.md) and the [current validation record](../history/validation-failure-drills.md).

## Original phase, query and concurrency tests

`tests/test_resilience_integration.py` exercises real Docker containers and PostgreSQL restores. It is opt-in and requires the normal package dependencies, a running local Docker engine, and the approved PostgreSQL image. Run with `RESTOREPROOF_INTEGRATION=1`; set `RESTOREPROOF_EVIDENCE_DIR` to retain synthetic fixtures, journals, worker logs, and summaries.

```text
python -m unittest discover -s tests -p test_resilience_integration.py -v
```

Four tests cover:

1. Hard termination inside the engine's restore phase, after real `pg_restore` has completed and before the adapter returns.
2. Hard termination inside the checks phase, after the first real SQL assertion has executed and before its result returns.
3. Hard termination while a tagged SQL query is actually executing `pg_sleep(60)`. The parent must observe that exact query in `pg_stat_activity` with `state=active`, `wait_event_type=Timeout`, and `wait_event=PgSleep` before killing the verifier tree. Observation has a 12-second deadline; the test must terminate the worker before its full sleep and finish the drill within 120 seconds.
4. Two verifier processes using one output directory, with both targets alive simultaneously. The first finishes and cleans up while the second stays paused; the second then finishes independently.

A subclass defined only in the test provides deterministic checkpoints and the deliberately slow read-only query. The first two interruption tests pause after real operations; the third proves an in-flight query through server-side observation. They do not claim to kill `pg_restore` during database writes. The interrupted journal must remain `INCOMPLETE`, even after a fresh cleanup adapter removes the target. Repeating cleanup must verify absence. A separately labelled, test-owned container must survive each recovery and is removed by the test's own final cleanup.

Workers use dedicated process groups on POSIX and a separate process group on Windows. Hard termination targets only that worker's process tree (`taskkill /PID /T /F` on Windows; `SIGKILL` to its dedicated group on POSIX). Polling, checkpoints, subprocesses, and final cleanup are bounded. Finalizers recover targets from journals and remove only the test's specifically labelled foreign fixture. No daemon restart, global prune, or unrelated container cleanup occurs.

Retained `interruption.json` or `concurrency.json` describes successful assertions; `test-cleanup.json` records final cleanup. A saved summary alone is not a suite-pass claim: check the test runner result and cleanup record together. Failure logs and unfinished journals remain diagnostic evidence. Short scenario directory names keep retained evidence usable on Windows; choose a short evidence root when Windows path-length limits apply.

## Recorded local result

All **four tests passed together in 69.311 seconds** in their original Windows run with Docker Desktop's Linux engine. The in-flight query test observed `state=active`, `wait_event_type=Timeout`, and `wait_event=PgSleep` before killing its verifier at 8.516 seconds into that drill. All three interrupted journals remained `INCOMPLETE`; owned-target recovery and repeated cleanup passed, unrelated fixtures remained running, and final fixture cleanup passed. Both overlapping verifiers finished `PASS` with distinct run IDs and containers, with the second target surviving the first run's cleanup. These four tests were subsequently included in the historical [v0.2 validation](../history/validation-v02.md).

## Actual COPY interruption

`tests/test_restore_write_integration.py` adds two real verifier paths: hard-kill the CLI during observed COPY, or terminate the observed PostgreSQL backend while leaving the verifier alive. The latter must return exit 2/INCOMPLETE, attribute the error to restore, run no downstream checks, and clean up automatically. A test-only wrapper delays normal cleanup until the observer receives its real control SQL response; restore, checks, status evaluation and cleanup still use the production implementations. A missing or mismatched response cannot become a passing handshake.

The small trusted fixture pauses COPY at a bounded test-only CHECK/advisory-lock gate. An observer must see active COPY FROM/PIPE and `0 < tuples_processed < 2048` before the fault. The corrected local paired run passed both tests in 48.107 seconds; the drills observe 1,000 processed rows. Each test then completes a healthy run of the same archive, preserves an unrelated test container, and verifies final cleanup. Both tests also passed in the successful Ubuntu run (pre-release CI run 37517902305). This is uncommitted work within `pg_restore`'s single transaction; it does not measure loss of committed data. See [fixture details](failure-drills.md) and [revision-specific evidence](../history/validation-failure-drills.md).

## Separate daemon outage

The Linux-only daemon test creates a private daemon and native containerd, then stops only the verified daemon process with controlled `SIGTERM`, with `live-restore=false`. Its fault is Docker API unavailability at a checkpoint after restore, not a concurrent active-COPY fault. Restart and later cleanup must leave the original failed journal INCOMPLETE. The runner's original daemon and sentinel are checked separately; the user's Docker Desktop is never restarted.

The live daemon test passed in Ubuntu CI (pre-release CI run 37517902305). The owned daemon stopped with exit 0; verification and cleanup were INCOMPLETE while its API was unavailable. After restart, the target was exited; recovery, repeated absence checks and final cleanup passed, with the original daemon and sentinel unchanged. The [validation record](../history/validation-failure-drills.md) preserves the failed journal separately from later cleanup evidence. Abrupt daemon crashes, power loss and uninterrupted data-plane operation remain outside this fault model.
