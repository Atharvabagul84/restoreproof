# 0002: Authorization in PostgreSQL row-level security

**Status:** Accepted

## Context
Team workspaces hold shared briefs. Supabase exposes the database API directly, so checks only in Next.js route handlers could be bypassed with the publishable key.

## Decision
Workspace roles are enforced in PostgreSQL: row-level security on every table, and all writes through restricted RPCs whose implementations live in an unexposed private schema. The app uses only the publishable key, verifies every protected request with `getUser()`, and never trusts client role fields or user-editable JWT metadata. Saves carry an expected revision and create immutable snapshots.

## Consequences
- Direct API calls get the same answer as the app.
- Policies and RPCs are tested on a real PostgreSQL engine (PGlite) in CI.
- New tables or writes need a migration with policies and an RPC, not just a route.
