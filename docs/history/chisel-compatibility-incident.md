# Recovery drill finding: revision-conflict retry loop

## Trigger and observation

The first complete Chisel journey used PostgREST 14.17, taken from the pinned Supabase self-hosted profile. The fresh database restored successfully. Real email OTP login worked; the recovered owner and saved brief digest matched. Creating, reading and updating a new brief also reached the database.

The next operation deliberately submitted a stale revision. Chisel's unchanged SQL raises `40001` for this application-level conflict. The local PostgreSQL logs then repeated `CHISEL_REVISION_CONFLICT` until the bounded HTTP probe timed out. RestoreProof correctly reported **INCOMPLETE**, with the four checks completed before the write cycle retained. Owned cleanup passed and stopped the looping local backend.

Historical local run: `3cfb48f1d6d140b8b8c0a41a6303b1e0`. Its unedited report is retained under `evidence/chisel/postgrest14-regression/`. This was a disposable synthetic drill; no conclusion about Chisel's deployed Supabase version or production traffic was made.

## Root cause and resolution

PostgREST's [upstream issue #3673](https://github.com/PostgREST/postgrest/issues/3673) describes unbounded retries for SQLSTATE `40001`. Supabase's [September troubleshooting note](https://github.com/orgs/supabase/discussions/50151) identifies the same behavior for custom RPC exceptions in PostgREST 14 and notes the fix in version 16. The [PostgREST changelog](https://github.com/PostgREST/postgrest/blob/main/CHANGELOG.md) records that fix.

The lab profile was upgraded to digest-pinned **PostgREST 16.4**. Chisel's source and SQL migrations stayed byte-for-byte unchanged. The repeated healthy drill returned HTTP **409** for the stale write, then verified the newer content was unchanged. Tenant isolation and sign-out also passed.

This choice fixes the lab dependency incompatibility without altering the application being recovered. For a deployed Chisel stack, first inspect the actual PostgREST version. A separate application change could use a dedicated non-retryable error such as `PT409` and update Chisel's controller mapping accordingly; that migration is outside this adapter milestone and has not been applied to a hosted project.
