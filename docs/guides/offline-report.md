# Offline recovery evidence report

`report-html` creates one self-contained HTML file from retained S3 recovery journals. It requires no AWS session, Docker daemon, web server or external assets. It does not rerun recovery.

```sh
python -m restoreproof report-html \
  --input evidence/aws-live --input evidence/v05/ci \
  --output runs/recovery-report.html
```

Open the output directly in a browser. Repeat `--input` for multiple directories or individual JSON reports. Directory inputs search for `report.json`; nested source/application journals are excluded from the S3 attempt count. Historical paths inside JSON are never followed. To report a fresh local demo:

```sh
python -m restoreproof s3-demo --output runs/showcase-s3
python -m restoreproof report-html \
  --input runs/showcase-s3 --output runs/showcase-s3.html
```

## How to read it

- AWS, loopback S3 and unclassified storage each get a separate history, latest attempt and last success. Scope comes from the recorded endpoint; it is not independent cloud-identity verification.
- Latest attempt can be FAIL or INCOMPLETE while an earlier successful run remains visible. Controlled negative cases keep their actual unsuccessful status even when the overall test suite passes.
- Expand a run to inspect its pinned object/version, SHA-256, capture time, age **at verification**, checks, recorded HTTP outcomes, cleanup and timings.
- A missing backup identity, missing success or unfinished journal stays explicit. A historical PASS does not mean the backup is still fresh today.
- Input JSON fingerprints allow comparison with the original bytes. They are not signatures, and the report does not authenticate the evidence producer.

Export success has its own JSON field, `export_status`. A successful HTML export is not a successful recovery. stdout also contains the selected scopes and their latest/last-success run identities. An invalid evidence set returns exit 3 and leaves an existing output untouched.

The reader rejects contradictory successful records, mismatched successful retrieval receipts, duplicate keys, non-finite numbers, conflicting copies of the same run, files over 256 KiB, and selections containing more than 200 report files before deduplication. Identical duplicate runs are counted once. Explicit symlink inputs and symlink journal files are rejected. Inputs should still come from a trusted local evidence directory.

Only selected fields are rendered and all text is escaped. Raw error messages, credentials and local paths are omitted. Object names, version IDs, hashes and run IDs remain visible; a private source can still produce a private report. No scripts, fonts, stylesheets or images are fetched. Native disclosures work with keyboard controls, and the table can scroll on narrow screens. Expand the desired run records before printing or saving to PDF.

## Weekly synthetic recovery lab

The existing `Recover Chisel from S3` workflow supports both manual `local-lab` runs and an independent, opt-in weekly lab schedule. Both require this exact repository (`RESTOREPROOF_REPOSITORY_ID` must equal `github.repository_id`) on `main` and `RESTOREPROOF_FREE_CI_VERIFIED=true`. The timer additionally requires `RESTOREPROOF_LAB_SCHEDULE_ENABLED=true`.

The scheduled job captures fresh synthetic Chisel data, uploads versions to loopback Moto, executes the six recovery/failure scenarios, renders the current job's evidence and uploads JSON/JUnit/HTML. The job uses a standard Ubuntu runner, a 25-minute timeout and a non-cancelling concurrency group. It needs only repository read access; the issuer-identity job runs only on manual lab dispatches. AWS role and AWS schedule gates stay independent.

Schedule: **Monday 04:17 UTC / 09:47 India time**. GitHub scheduling is best-effort; a configured timer or a manual run is not proof that a scheduled event has already executed.

The lab flag was enabled and read back on **October 7, 2026**, after [manual validation passed](../history/validation-v05.md). The first scheduled execution is due October 12 and was still pending at handoff. AWS flags remain unset.

Download the private artifact `s3-chisel-local-lab`, then open `report/restoreproof.html`. Artifacts expire after **one day**. Each report's history covers the selected journals, not previous weekly jobs; GitHub's workflow run list separately records job outcomes. Retain reviewed evidence locally or in the private repository when it must outlive the artifact. The workflow does not commit evidence automatically.

To pause the lab, unset `RESTOREPROOF_LAB_SCHEDULE_ENABLED` or set it to `false`. Disable the shared free-CI gate if account eligibility or enforced spending protection changes. See [the cost policy](../reference/cost-policy.md). An enabled lab timer does not enable AWS OIDC or cloud recovery.
