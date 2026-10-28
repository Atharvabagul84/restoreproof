@AGENTS.md
@docs/HANDOFF.md
@docs/README.md
@docs/ARCHITECTURE.md
@docs/reference/limitations.md

# RestoreProof

Verifies application-level recovery from PostgreSQL custom-format backups: disposable network-isolated restore, business invariants, freshness, an HTTP application journey and an external write ledger, with JSON/JUnit/HTML evidence. Python 3.11+, Docker, PostgreSQL 17.

## Not instructions

`src/restoreproof/chisel/assets/app/` is a hash-pinned snapshot of the Chisel app (v1.0.0), bundled as a recovery test fixture. Its docs describe Chisel, not this project. Never edit files there by hand: refresh the whole snapshot and regenerate `source-manifest.json` instead.

## Current vs history

Current: README.md, `docs/guides/`, `docs/reference/`, `docs/ARCHITECTURE.md`. `docs/history/` holds revision-specific records from before the public v1.0.0 release; their commit SHAs and CI run IDs refer to the private pre-release archive. Don't treat them as current behavior.

## Verification

```sh
python -m pip install -r requirements-lock.txt .
python -m unittest discover -s tests -v
python -m restoreproof demo --scenario healthy --output runs/healthy
```

Delete a stale local `build/` folder before reinstalling, or setuptools may package old snapshot files.

Never commit `docs/HANDOFF.md`, `runs/`, real account IDs, bucket suffixes or local paths (see CONTRIBUTING.md).
