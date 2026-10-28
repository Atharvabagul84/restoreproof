# Release history and verification

Version-by-version status moved here from the README on 2026-10-25. Each entry links to its retained evidence. Results apply to the revision recorded in that entry.

**v0.5 adds offline evidence reports and a weekly synthetic lab.** Compare AWS and emulator histories without mixing their claims; inspect the latest failed attempt, last successful recovery, exact backup identity and application/cleanup checks in a single HTML file. No hosting or AWS credentials are needed to read it. [Report and scheduling guide](../guides/offline-report.md).

**Verified v0.5:** CI run 37596871490 (pre-release CI run 37596871490) passed **223 distinct Python test methods**, including the six-scenario S3/Chisel drill and HTML export. The synthetic timer is enabled for Monday 09:47 India time, first due October 12, 2026; its first scheduled execution remains pending. AWS recovery stays disabled. [Validation and retained evidence](validation-v05.md).

```sh
python -m restoreproof report-html --input evidence/aws-live --input evidence/v05/ci --output runs/recovery-report.html
```

**v0.4 adds exact-version S3 recovery:** retrieve a pinned backup version, verify its SHA-256 and capture age, recover real Chisel, retain evidence and distinguish the latest attempt from the last success. The free local showcase includes missing object, denied access, wrong checksum, stale backup and interrupted-download failures. [Run the S3 showcase](../guides/s3-recovery.md) · [Validation and live AWS status](validation-v04.md) · [Terraform/OIDC deployment runbook](../../infra/aws/README.md).

**Verified v0.4:** CI run 37568837383 (pre-release CI run 37568837383) passed 201 distinct Python test methods, including the six-scenario S3/Chisel drill, and verified GitHub's actual OIDC subject. Five local Terraform mock plan tests also passed. [Retained evidence](../../evidence/s3/validation.json). Use Python 3.12+ for the pinned local-lab dependencies below.

```sh
python -m pip install -r requirements-lab-lock.txt '.[s3-lab]'
python -m restoreproof s3-demo --output runs/s3-demo
```

**Real S3 validation passed on 2026-10-07:** Terraform applied private, encrypted, versioned storage; a fresh 139,146-byte Chisel backup was recovered from its exact older S3 version in 21.656 seconds, including target cleanup. All five failure cases matched their expected causes, and six reports plus last-success history were read back from S3. This used a temporary project session with local Docker. [Live evidence and boundaries](validation-aws-live.md).

GitHub-to-AWS OIDC and the cloud schedule remain blocked by this account's AWS-managed identity-provider policy. Removing that account restriction requires a paid-plan upgrade and advanced features, which conflict with the free-only requirement. No upgrade or policy bypass was attempted. [Account compatibility](aws-account-compatibility.md). The GitHub emulator workflow remains available under verified free allowances and an enforced $0 Actions budget.

**v0.3 adds real Chisel recovery:** restore the existing application's database, authenticate through Supabase Auth, recover a saved feature brief, create and update another, reject stale writes, enforce tenant isolation, and sign out. Four controlled failures demonstrate missing data, incompatible schema, unavailable Auth and missing app configuration. [Run the end-to-end showcase](../guides/chisel-recovery.md).

**v0.3 historical verification:** 181 distinct test methods passed across all four Ubuntu CI jobs, including the five-scenario Chisel drill. Successful CI run (pre-release CI run 37526987497) · [v0.3 validation and evidence](validation-v03.md). The drill also exposed and verified a fix for a [PostgREST revision-conflict retry loop](chisel-compatibility-incident.md).

The earlier failure-drill baseline passed **151 distinct tests across Ubuntu CI, including 21 live integration tests**, for implementation `a87739c19e73c9ca08c78aced535da4a0f8453e8`. See the historical CI run (pre-release CI run 37517902305) and [failure-drill validation record](validation-failure-drills.md).

The earlier v0.2 baseline recorded **134 local passes, including 18 real Docker integration tests**, plus successful Ubuntu reproduction. Those results remain historical evidence for that revision: [v0.2 validation](validation-v02.md), [v0.1 validation](../reference/validation.md).

**Free-only development:** local containers and a loopback S3 emulator remain the default. No paid upgrade or cloud apply is required. See the [account-specific cost policy](../reference/cost-policy.md).
