# 0003: Hosted runs gated on verified free usage

**Status:** Accepted

## Context
Integration drills and S3 recovery can run on GitHub-hosted runners and AWS. Free allowances expire or change, and a budget alert alone doesn't stop charges.

## Decision
Hosted integration jobs run only when the repository variable `RESTOREPROOF_FREE_CI_VERIFIED` is exactly `true`, and the scheduled lab only when `RESTOREPROOF_LAB_SCHEDULE_ENABLED` is set. They're enabled only after the actual account's allowance, expiry and enforced overage prevention have been checked. AWS scheduling stays off until its own authentication and fresh-backup prerequisites pass. Everything else runs locally against Docker and emulators. See the [cost policy](../reference/cost-policy.md).

## Consequences
- No surprise charges; a skipped job is reported as skipped, never as evidence.
- Local emulator results are not claimed to validate real AWS IAM, OIDC or hosted recovery.
