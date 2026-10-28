# Security policy

## Supported versions
Only the latest release on `main` is supported.

## Reporting a vulnerability
Please **don't open a public issue**. Use GitHub's [private vulnerability reporting](https://github.com/Atharvabagul84/restoreproof/security/advisories/new). Include what you found, how to reproduce it and the expected impact. You'll get a reply within 7 days.

## Threat model in brief
- RestoreProof runs trusted contracts, archives and images through a privileged Docker daemon. It isolates the restore target (no network, dropped capabilities, resource limits) but **is not a sandbox for hostile code**.
- It never connects to an existing database URL; every target is created and owned by the run.
- Reports can contain values returned by your SQL checks. Use synthetic data for demos and review evidence before sharing it.

In scope: escaping the target's isolation, cleanup deleting resources the run doesn't own, a contract or archive that makes a failed recovery report PASS, and credential exposure in evidence or logs.

## Handling secrets
- No credentials, real AWS account IDs, bucket suffixes, Terraform state or local paths belong in this repository. Secret scanning and push protection are enabled.
- AWS access in CI uses GitHub OIDC (no stored keys) and stays disabled unless free usage is verified (see [ADR 0003](docs/decisions/0003-free-usage-gate.md)).
