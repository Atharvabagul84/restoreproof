# 0003: Free-tier hosted demo with fail-closed limits

**Status:** Accepted (2026-10-27)

## Context
Production generation returned HTTP 503 because a public paid key has no spending cap. Visitors to the hosted preview couldn't see the core feature. Email sign-in for per-user quotas isn't set up yet.

## Decision
Allow anonymous hosted drafts only when all of these are configured: `CHISEL_GENERATION_PROVIDER=groq` (free tier, no billing), `CHISEL_HOSTED_DEMO=true`, a Groq key, and Upstash Redis limits with a visitor salt. Requests must come from the app's own origin. Limits are 3 drafts per visitor per day (salted SHA-256 of the IP), then 100 per day in total; the visitor limit is checked first. Upstash errors and its fail-open `timeout` result both close generation (503). Paid Anthropic generation is never opened to anonymous visitors.

## Consequences
- No spend risk; the worst case is the free provider's own rate limit (`provider_busy`).
- Raw IP addresses are never stored.
- Briefs go to Groq, so the UI tells visitors not to paste confidential information.
- Turning the demo off is one environment variable and a redeploy.
