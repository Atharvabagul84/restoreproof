# Product Requirements Document

## 01 Product Overview
- **Product Name:** RestoreProof
- **Tagline:** Row counts aren't recovery.
- **Description:** A verifier that restores a PostgreSQL backup into a disposable, network-isolated container and proves the application recovered: business invariants, data freshness, a real read/write journey through the app, and exact accounting of lost writes. Every run leaves JSON, JUnit and HTML evidence. It builds on `pg_restore`; it is not a backup engine.

## 02 Problem
- A restore can exit 0 and still break the application: a violated business rule, data older than the recovery objective, or missing acknowledged writes.
- Typical backup checks stop at "the restore finished" or row counts, and leave no evidence a reviewer can inspect.

## 03 Goal
- For a given backup, answer "would the application work, and what was lost?" with a reproducible PASS / FAIL / INCOMPLETE / INVALID outcome and its evidence.

## 04 Target Users
- SRE and platform engineers who own PostgreSQL backups
- Teams running restore drills before audits or incidents
- Reviewers who need evidence, not assurances

## 05 Core Features (Version 1)
- **Disposable isolated restore:** verifier-owned container, no network, dropped capabilities, ownership-checked cleanup.
- **Declarative checks:** strict JSON contracts with business invariants and freshness (RPO) policy.
- **External write ledger:** exact missing or changed acknowledged writes.
- **Application journey:** HTTP read/write and tenant isolation through a real app (bundled Chisel).
- **S3 source:** exact object versions from AWS S3 or a local emulator.
- **Evidence:** JSON journal, JUnit XML, offline HTML report; failure and interruption drills.

## 06 Out of Scope (for now)
- Physical backups, WAL/PITR, replication, regional recovery
- Arbitrary-application journey plugins
- Large-dataset performance or production RTO claims
- Accepting existing production database URLs

## 07 Success Metrics
- Every scenario (healthy and each failure type) produces its documented exit code in CI.
- Failure drills: an interruption or daemon loss always ends INCOMPLETE, never PASS, and cleanup recovers owned resources.
- Zero paid cloud usage (see the cost policy).
