# v0.3 validation: real Chisel recovery

**Validated implementation:** `38abf3835c318911ce9bf3a6729a092810f12abe`.

**All four jobs passed** in GitHub Actions run 37526987497 (pre-release CI run 37526987497): unit checks, normal PostgreSQL integration, isolated daemon-outage recovery, and Chisel application recovery. The repository is private.

## Test accounting

| Coverage | Distinct passing test methods |
|---|---:|
| Unit/guard checks | 159 |
| Ordinary live PostgreSQL integration | 20 |
| Live isolated-daemon outage | 1 |
| Live Chisel recovery method, covering five end-to-end scenarios | 1 |
| **Total across CI, deduplicated** | **181** |

The unit job discovers 181 methods, passes 159 and intentionally skips 22 live methods. The other three jobs exercise those live methods. Repeated guard methods are counted once. The five Chisel scenarios are five drill outcomes within one integration-test method, not five extra methods. [Curated CI test output](../../evidence/chisel/ci-tests.log) retains the observed names and summaries; [machine-readable validation](../../evidence/chisel/validation.json) records the accounting and provenance.

## Observed recovery results

Both Windows Docker Desktop (Linux engine) and Ubuntu CI produced this matrix:

| Scenario | Actual recovery outcome | Expected failure proved | Source cleanup | Target cleanup |
|---|---|---|---|---|
| Healthy | PASS | Full login, read, create/update, conflict, isolation, sign-out journey | PASS | PASS |
| Missing data | FAIL | Expected saved brief absent; restored identity and new writes work | PASS | PASS |
| Incompatible schema | FAIL | Required save RPC absent; existing identity/data remain readable | PASS | PASS |
| Auth unavailable | INCOMPLETE | Owned Auth container observed stopped; email login cannot complete | PASS | PASS |
| Missing configuration | INCOMPLETE | Chisel refuses email login with HTTP 503 | PASS | PASS |

Each environment's five-scenario suite created **60 distinct owned containers** across ten source/target stacks. Every recorded cleanup passed. Reports include the actual container IDs, observed Docker isolation settings, image IDs, per-phase timings and individual application outcomes.

The final CI suite also requires the **specific injected failure cause** to match. A restore or startup error cannot be accepted merely because an Auth-unavailable scenario expected INCOMPLETE. Interruption stops further scenario allocation after cleanup. Local reports were captured before this final suite-verdict guard and were re-evaluated successfully with the final guard; the CI run executes the exact implementation revision above.

## Timing and interpretation

The recorded healthy target verification took **26.218 seconds locally** and **4.811420 seconds in Ubuntu CI**. These are individual observations for a tiny synthetic dataset. They include contract preflight, fresh database provisioning, restore, dependency startup and application checks. Source seeding, backup capture and image preparation are excluded; cleanup is separate.

These measurements do not establish production RTO/RPO, incident MTTR or a performance benchmark. Failed/incomplete attempt durations are not successful recovery times.

## Additional checks

- The built Python wheel was installed outside the repository and verified all 101 pinned Chisel source files from package data.
- The existing database adapter still strips owner/ACL metadata; the Chisel adapter preserves it after provisioning fixed disposable roles. Existing unit and live PostgreSQL regression jobs passed.
- Ownership tests refuse foreign labels, renamed/replaced resources, unknown existing components and ambiguous daemon state. Evidence guards reject incomplete/duplicate check sets, invalid statuses and unsafe runtime settings.
- The package has no production database endpoint input and no external runtime network. Chisel, GoTrue, PostgREST, Mailpit and TLS gateway run inside the disposable database namespace.
- Backups, auth cookies, OTPs, generated passwords and TLS private keys are excluded from committed evidence and CI artifacts. The source snapshot and repository remain private.

## Evidence navigation

- [CI healthy report](../../evidence/chisel/ci/healthy/target/report.json)
- [CI missing-data report](../../evidence/chisel/ci/missing-data/target/report.json)
- [CI incompatible-schema report](../../evidence/chisel/ci/incompatible-schema/target/report.json)
- [CI Auth-unavailable report](../../evidence/chisel/ci/auth-unavailable/target/report.json)
- [CI missing-config report](../../evidence/chisel/ci/missing-config/target/report.json)
- [Local healthy report](../../evidence/chisel/local/healthy/target/report.json)
- [Evidence SHA-256 manifest](../../evidence/chisel/MANIFEST.json)
- [Dependency compatibility finding and resolution](chisel-compatibility-incident.md)

Reports are copied byte-for-byte. Their embedded original filesystem paths remain historical provenance; use the relative links above to open curated copies. Source-capture reports, pre-fault expectations and JUnit companions sit alongside each target report. JUnit for an intentional failure remains a failure/error report; the suite summary separately records whether the negative experiment matched its intended cause.
