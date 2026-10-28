# Evidence

Recorded outputs of RestoreProof runs (JSON journals, JUnit, manifests, logs), kept as they were produced so their checksums still match.

- **Immutable.** Don't edit these files; a new run produces new evidence. Some manifests fingerprint other files here.
- **Pre-release references.** Commit SHAs, CI run IDs and Actions URLs inside these files come from the private pre-release development archive, so the URLs aren't publicly reachable. This public repository starts at v1.0.0.
- **Redacted identifiers.** Before publication, the real AWS account ID was replaced with `123456789012`, lab bucket suffixes with `restoreproof-lab-example`, and local paths with `<workspace>`. Nothing else was changed: outcomes, timings, failure causes and object checksums are as recorded.
- **Synthetic data only.** No production data, backup archives, Terraform state, cookies, OTP values, private keys or credentials.

Read the matching record in [`docs/history/`](../docs/history/) for what each run does and doesn't show.
