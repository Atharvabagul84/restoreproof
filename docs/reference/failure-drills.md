# Active restore and isolated-daemon failure drills

These experiments extend the v0.2 interruption tests. They answer two separate questions: what happens when a restore is interrupted after processing rows, and what happens when the verifier loses its Docker daemon during a run?

## Observe a restore before interrupting it

The small synthetic archive contains a test-only CHECK function that pauses partway through COPY using a bounded advisory-lock handshake. The source fixture bypasses the gate while seeding. On restore, the observer requires an active COPY FROM operation with a positive processed-row count before injecting a fault. It does not infer progress from a timer, process creation, or the size of the archive.

PostgreSQL exposes COPY progress through pg_stat_progress_copy. The recorded rows are processed within pg_restore's single transaction; they are not evidence of committed or durable partial recovery. A separate session cannot safely infer that progress from the table's row count while the restore transaction is uncommitted. [PostgreSQL 17 progress reporting](https://www.postgresql.org/docs/17/progress-reporting.html)

The drill includes two fault boundaries:

- Hard termination of the owned verifier process tree: its saved journal must stay INCOMPLETE. A fresh cleanup adapter removes its target, repeated cleanup confirms absence, and an unrelated test container survives.
- Termination of the observed PostgreSQL backend: the CLI stays alive to handle the failed pg_restore command. Its final result must be INCOMPLETE with exit 2, no completed verification checks, and successful owned cleanup.

Each experiment also verifies a fresh run using the same archive and deliberately releases the fixture gate. A valid healthy control must pass; an invalid archive cannot masquerade as successful fault injection. Failure to observe the active-write gate fails the drill. The gate exists only in test fixtures and is not a production recovery mechanism.

For the backend-termination and healthy-control paths, a test-only worker delays target cleanup until the controlling SQL session has returned. Otherwise a fast verifier can remove the container before PostgreSQL's termination acknowledgement reaches the observer. The barrier changes only test scheduling: restore and verification use the actual CLI, the normal cleanup implementation still runs, and a missing or invalid release fails the test. The hard-kill path invokes the CLI directly.

```sh
RESTOREPROOF_INTEGRATION=1 RESTOREPROOF_EVIDENCE_DIR=runs/failure-drills \
  python -m unittest discover -s tests -p test_restore_write_integration.py -v
```

On PowerShell, set the two environment variables with `$env:NAME = 'value'`, then run the same Python command.

## Remove a separate Docker API

The daemon drill runs as root only on a disposable Linux CI runner. It starts a second native dockerd with its own socket, config, PID file, data and execution directories, containerd namespaces and cgroup parent. A separately spawned containerd has its own explicit root, state, socket and configuration; Docker receives that nonempty private socket instead of auto-discovering the system runtime. The helper verifies process ownership, private runtime readiness, configuration paths and Docker's classic storage configuration. Containerd CRI/TCP/metrics and Docker bridge/firewall/IP-forwarding changes are disabled, and test containers use network none. Docker describes multiple-daemon operation as experimental; this is a bounded experiment on the recorded runner, not a recommended production deployment topology. [Docker daemon reference](https://docs.docker.com/reference/cli/dockerd/#run-multiple-daemons)

The verifier first restores a real target and retains an incomplete journal. The harness sends SIGTERM only to its verified, spawned daemon process. Live restore is disabled deliberately: stopping this private daemon can also stop its own containers. The claim is a controlled daemon-API outage, not independent data-plane survival or power-loss recovery.

While that endpoint is unavailable, verification and attempted cleanup must remain INCOMPLETE. The harness restarts the daemon using the same private directories, recovers the exact run's cleanup, and verifies absence again. Later cleanup is separate evidence; it must never rewrite the failed verification as PASS. The runner's original daemon identity and an unrelated running sentinel are checked before and after the experiment.

The [isolated-daemon CI job](../../.github/workflows/validate.yml) is the supported reproduction entry point. Its explicit opt-in is `RESTOREPROOF_DAEMON_INTEGRATION=1`. Normal test discovery skips the live daemon drill; explicit enablement with missing Linux/root/docker/dockerd/containerd/ctr/runc prerequisites fails. Ownership and configuration guard tests run without starting a daemon.

Runtime state stays outside the uploaded evidence directory. Only curated JSON/XML and bounded diagnostic logs are retained. No global prune, system Docker service stop, or Docker Desktop restart is part of either drill.

## Interpreting results

Use the suite result, progress observation, fault record, final journal and cleanup record together. A JSON file alone does not establish that an experiment passed. Full host loss, abrupt daemon crashes, live-restore data-plane continuity, physical/WAL recovery and production RPO/RTO remain separate questions.
