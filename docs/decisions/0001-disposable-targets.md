# 0001: Disposable, verifier-owned targets only

**Status:** Accepted

## Context
A restore verifier with database access could be pointed at a real database by mistake, and leftover containers make later runs ambiguous.

## Decision
RestoreProof never accepts an existing database URL. Every run creates its own PostgreSQL container with no network, no published ports, no host mounts, dropped capabilities (except CHOWN, FOWNER, SETGID, SETUID), `no-new-privileges`, resource limits and tmpfs storage. A persistent journal records what the run intends to create and did create. Cleanup deletes only containers it can prove it owns, then verifies they are gone.

## Consequences
- A contract can't damage a production database.
- A cleanup failure forces INCOMPLETE even after passing checks, and `cleanup RUN_ID` can finish the job later.
- Docker access is still privileged: contracts, archives and images must be trusted. This is not a hostile-code sandbox.
