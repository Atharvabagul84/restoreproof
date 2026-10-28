# 0001: One bounded, schema-validated LLM call

**Status:** Accepted

## Context
Chisel drafts a spec from a brief. Agent loops, tool calling and prompt chains add cost, latency and failure modes, and make output harder to trust. A failed or malformed draft must never look like a real one.

## Decision
Each "Generate" is exactly one model request behind the `CompleteFeatureSpec` adapter type (`lib/server/`). Input and output are validated with Zod at both edges (`lib/feature-spec.ts`). The request has a 64 KiB body cap, a 45-second deadline, caller cancellation and no retries. Output must finish cleanly and parse as the full schema, or the user sees a visible `invalid_output` error and keeps their brief.

## Consequences
- Providers are swappable adapters (Anthropic locally, Groq for the hosted demo) without touching the service or the checks.
- Schema validation checks structure and bounds, not truth; people review every draft.
- No sample document is ever returned in place of a failed generation.
