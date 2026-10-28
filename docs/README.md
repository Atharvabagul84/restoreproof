# RestoreProof documentation

## Project
- [Product requirements](PRD.md): why RestoreProof exists, users, v1 scope
- [Architecture](ARCHITECTURE.md): stack, structure, verification flow, outcome contract
- [Design system](DESIGN_SYSTEM.md): the offline HTML evidence report

## Guides
- [Usage](guides/usage.md): commands, contracts, exit codes
- [Chisel application recovery](guides/chisel-recovery.md): the real-application journey
- [S3 recovery](guides/s3-recovery.md): exact-version retrieval from S3 or an emulator
- [Offline HTML report](guides/offline-report.md): build and read the evidence report

## Reference
- [Limitations](reference/limitations.md) · [Acceptance checklist](reference/acceptance.md) · [Validation](reference/validation.md)
- [Write ledger](reference/ledger.md) · [Failure drills](reference/failure-drills.md) · [Interruption drill](reference/interruption-drill.md)
- [Cost policy](reference/cost-policy.md): free-only rules for hosted runs

## Decisions
- [0001 Disposable, verifier-owned targets only](decisions/0001-disposable-targets.md)
- [0002 Write ledger kept outside the backup](decisions/0002-external-write-ledger.md)
- [0003 Hosted runs gated on verified free usage](decisions/0003-free-usage-gate.md)

## History
[`history/`](history/) holds revision-specific validation records and findings from before the public v1.0.0 release (start with [release history](history/release-history.md)). Their commit SHAs and CI run IDs refer to the private pre-release archive. Recorded run evidence is in [`evidence/`](../evidence/).
