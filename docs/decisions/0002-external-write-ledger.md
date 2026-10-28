# 0002: Write ledger kept outside the backup

**Status:** Accepted

## Context
Checking a restored database against data derived from the same backup can only confirm the backup agrees with itself. It can't show which acknowledged writes are missing.

## Decision
An optional ledger, recorded independently of the archive, lists a closed set of acknowledged writes with identities and payload hashes. After restore, RestoreProof recomputes hashes from recovered rows and compares: missing, duplicate, unexpected or altered records fail; unreadable recovered evidence is INCOMPLETE. Expectations are never regenerated from restored data.

## Consequences
- The report can say exactly which writes were lost, within the ledger's scope.
- Coverage is only as complete as the ledger; digest matches show byte identity, not recorder authenticity.
- Concurrent writers and ambiguous commit acknowledgements need further design (see [limitations](../reference/limitations.md)).
