# Contributing

Issues and pull requests are welcome.

## Setup
- Python 3.11+ (3.12+ for the pinned local S3 lab) and Docker for integration tests

```sh
python -m venv .venv && source .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-lock.txt .
python -m restoreproof demo --scenario healthy --output runs/healthy
```

On Windows, enable long paths for the bundled Chisel snapshot: `git config core.longpaths true`. If you reinstall, delete a stale `build/` folder first.

## Checks (run before every pull request)
```sh
python -m unittest discover -s tests -v
```
Docker integration tests skip without Docker. CI also runs PostgreSQL integration, the private-daemon drill and Chisel recovery when hosted validation is enabled.

## Pull requests
1. Branch from `main`; one change per PR.
2. Add or update tests. Outcomes must stay honest: anything that prevents complete evidence is INCOMPLETE, never PASS.
3. Update the matching doc (and an ADR in `docs/decisions/` for a design change).
4. Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
5. `main` is protected: changes land by squash-merging a PR with green CI.

## Updating the bundled Chisel snapshot
Replace `src/restoreproof/chisel/assets/app/` with `git archive` of a Chisel commit (excluding `CLAUDE.md` and `AGENTS.md`), regenerate `source-manifest.json` (sorted paths, SHA-256 of bytes), verify every file against that commit, then update the commit in `chisel/contract.py`, both schemas and `tests/test_chisel.py`, and the file count in `tests/test_chisel_boundaries.py` and `docs/guides/chisel-recovery.md`. Leave evidence and historical contracts unchanged.

## Never commit
- Real AWS account IDs (use `123456789012`), bucket suffixes (use `restoreproof-lab-example`), absolute local paths (use `<workspace>`)
- Credentials, tokens, `.env` files, `*.tfstate`, `*.tfvars`
- `runs/` output or backup archives with non-synthetic data
- Edits to files under `evidence/` (they're immutable records)
