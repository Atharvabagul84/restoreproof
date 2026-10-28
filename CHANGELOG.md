# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] - 2026-10-28

First public release. Pre-release versions 0.1–0.5 were developed in a private archive; their validation records are in [docs/history/](docs/history/).

### Added
- Disposable, network-isolated PostgreSQL restore with ownership-checked cleanup and a crash-safe run journal.
- Strict JSON contracts: archive identity, business invariants, freshness (RPO) policy, duration objectives.
- External write ledger reporting exactly which acknowledged writes were lost or changed.
- HTTP application journey (read, write, tenant isolation) through a bundled Chisel v1.0.0 snapshot with GoTrue and PostgREST.
- Exact-version backup retrieval from AWS S3 or a local emulator.
- JSON, JUnit and self-contained offline HTML evidence; failure, interruption and private-daemon outage drills.
- GitHub Actions CI with hosted jobs gated on verified free usage.
- Documentation: PRD, architecture, report design system, guides, reference, decision records; security and contributing guides.

[Unreleased]: https://github.com/Atharvabagul84/restoreproof/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Atharvabagul84/restoreproof/releases/tag/v1.0.0
