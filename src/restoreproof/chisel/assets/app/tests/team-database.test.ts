import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { after, before, test } from "node:test";
import { PGlite } from "@electric-sql/pglite";
import { draftSchema } from "../lib/local-drafts";

// These tests execute the actual migration in PostgreSQL (PGlite), including
// RLS, grants, transactions and security-definer RPCs. The auth fixture is a
// minimal database interface, not a claim to test hosted Supabase Auth/email.
const owner = "10000000-0000-4000-8000-000000000001";
const engineer = "10000000-0000-4000-8000-000000000002";
const outsider = "10000000-0000-4000-8000-000000000003";
const unverified = "10000000-0000-4000-8000-000000000004";
const pm = "10000000-0000-4000-8000-000000000005";
const briefId = "20000000-0000-4000-8000-000000000001";
let db: PGlite;
let workspace: string;
let secondWorkspace: string;
let tokenCounter = 0;
const newToken = () => (++tokenCounter).toString(16).padStart(64, "0");
const validDraft = () => ({
  note: "", source: "manual", model: null, generatedAt: null,
  spec: { title: "", problem: "", targetUser: "", successMetric: "", inScope: [], outOfScope: [],
    userStories: [], acceptanceCriteria: [], assumptions: [], openQuestions: [], risks: [] },
});

async function asUser(user: string | null, sql: string, params: unknown[] = []) {
  return db.transaction(async (tx) => {
    await tx.query("select set_config('request.jwt.claim.sub', $1, true)", [user ?? ""]);
    // Put forged metadata in claims to prove role/email decisions use DB rows.
    await tx.query("select set_config('request.jwt.claims', $1, true)", [JSON.stringify({ sub: user, email: "owner@example.com", role: "owner" })]);
    await tx.exec(`set local role ${user ? "authenticated" : "anon"}`);
    return (await tx.query<Record<string, unknown>>(sql, params)).rows;
  });
}

async function invite(email: string, role = "engineer") {
  const token = newToken();
  const rows = await asUser(owner, "select public.chisel_create_invitation($1,$2,$3,$4) as id", [workspace, email, role, token]);
  return { id: rows[0].id as string, token };
}

async function save(user: string, id: string, revision: number, targetWorkspace = workspace, draft: unknown = {}) {
  const payload = draft && typeof draft === "object" && !Array.isArray(draft) ? { ...validDraft(), ...draft } : draft;
  const rows = await asUser(user, "select public.chisel_save_brief($1,$2,$3,$4::jsonb) as brief", [targetWorkspace, id, revision, JSON.stringify(payload)]);
  return rows[0].brief as { id: string; workspace_id: string; revision: number; draft: Record<string, unknown>; updated_by: string; updated_at: string };
}

before(async () => {
  db = new PGlite();
  await db.exec(await readFile(join(process.cwd(), "tests/fixtures/supabase-auth.sql"), "utf8"));
  await db.query("insert into auth.users values ($1,'owner@example.com',now()),($2,'Engineer@Example.com',now()),($3,'outsider@example.com',now()),($4,'unverified@example.com',null),($5,'pm@example.com',now())", [owner, engineer, outsider, unverified, pm]);
  const directory = join(process.cwd(), "supabase/migrations");
  const migrations = await readdir(directory).catch(() => [] as string[]);
  for (const file of migrations.filter((file) => file.endsWith(".sql")).sort()) {
    await db.exec(await readFile(join(directory, file), "utf8"));
  }
});

after(async () => { await db?.close(); });

test("the installed database exposes the workspace RPC only to authenticated users", async () => {
  const rows = await db.query<{ exists: boolean }>("select to_regprocedure('public.chisel_create_workspace(text)') is not null as exists");
  assert.equal(rows.rows[0].exists, true, "workspace creation RPC must be installed by the migration");
  await assert.rejects(asUser(null, "select public.chisel_create_workspace('Anonymous')"), /permission denied/i);
  await assert.rejects(asUser(unverified, "select public.chisel_create_workspace('Unverified')"), /verified|forbidden/i);
  await assert.rejects(asUser(owner, "select public.chisel_create_workspace('   ')"), /invalid/i);
  const result = await asUser(owner, "select public.chisel_create_workspace('Product team') as id");
  workspace = result[0].id as string;
  secondWorkspace = (await asUser(owner, "select public.chisel_create_workspace('Other team') as id"))[0].id as string;
  const membership = await asUser(owner, "select email, role from public.chisel_members where workspace_id=$1", [workspace]);
  assert.deepEqual(membership, [{ email: "owner@example.com", role: "owner" }]);
});

test("RLS hides every workspace table from outsiders and denies anonymous table reads", async () => {
  for (const table of ["chisel_workspaces", "chisel_members", "chisel_briefs", "chisel_brief_versions", "chisel_invitations"]) {
    assert.deepEqual(await asUser(outsider, `select * from public.${table}`), []);
    await assert.rejects(asUser(null, `select * from public.${table}`), /permission denied/i);
  }
});

test("only owners can invite and stored invitations contain hashed tokens", async () => {
  await assert.rejects(asUser(outsider, "select public.chisel_create_invitation($1,$2,$3,$4)", [workspace, "engineer@example.com", "engineer", newToken()]), /forbidden/i);
  await assert.rejects(invite("engineer@example.com", "owner"), /invalid/i);
  await assert.rejects(asUser(owner, "select public.chisel_create_invitation($1,$2,$3,$4)", [workspace, "engineer@example.com", "engineer", "weak-token"]), /invalid/i);
  const invitation = await invite("  engineer@example.com  ");
  const stored = await asUser(owner, "select email, token_hash, expires_at > now() as valid from public.chisel_invitations where id=$1", [invitation.id]);
  assert.equal(stored[0].email, "engineer@example.com");
  assert.match(String(stored[0].token_hash), /^[a-f0-9]{64}$/);
  assert.notEqual(stored[0].token_hash, invitation.token);
  assert.equal(stored[0].valid, true);
  await assert.rejects(asUser(outsider, "select public.chisel_accept_invitation($1)", [invitation.token]), /invitation/i);
  await asUser(engineer, "select public.chisel_accept_invitation($1)", [invitation.token]);
  await assert.rejects(asUser(engineer, "select public.chisel_accept_invitation($1)", [invitation.token]), /invitation/i);
  assert.deepEqual(await asUser(engineer, "select role from public.chisel_members where workspace_id=$1 and user_id=$2", [workspace, engineer]), [{ role: "engineer" }]);
  assert.equal((await asUser(engineer, "select * from public.chisel_workspaces")).length, 1);
  assert.deepEqual(await asUser(engineer, "select * from public.chisel_invitations"), []);
  await assert.rejects(asUser(engineer, "select public.chisel_create_invitation($1,$2,$3,$4)", [workspace, "pm@example.com", "pm", newToken()]), /forbidden/i);
});

test("expired, revoked, unknown, malformed and unverified invitations cannot be redeemed", async () => {
  const expired = await invite("pm@example.com", "pm");
  await db.query("update public.chisel_invitations set expires_at=now()-interval '1 second' where id=$1", [expired.id]);
  await assert.rejects(asUser(pm, "select public.chisel_accept_invitation($1)", [expired.token]), /invitation/i);
  const revoked = await invite("pm@example.com", "pm");
  await assert.rejects(asUser(engineer, "select public.chisel_revoke_invitation($1)", [revoked.id]), /forbidden/i);
  await asUser(owner, "select public.chisel_revoke_invitation($1)", [revoked.id]);
  await assert.rejects(asUser(pm, "select public.chisel_accept_invitation($1)", [revoked.token]), /invitation/i);
  for (const token of [newToken(), "bad"]) {
    await assert.rejects(asUser(pm, "select public.chisel_accept_invitation($1)", [token]), /invitation/i);
  }
  const notConfirmed = await invite("unverified@example.com");
  await assert.rejects(asUser(unverified, "select public.chisel_accept_invitation($1)", [notConfirmed.token]), /verified|forbidden/i);
});

test("joining an existing workspace cannot alter the user's existing role", async () => {
  const reinvite = await invite("engineer@example.com", "pm");
  await asUser(engineer, "select public.chisel_accept_invitation($1)", [reinvite.token]);
  assert.deepEqual(await asUser(owner, "select role from public.chisel_members where workspace_id=$1 and user_id=$2", [workspace, engineer]), [{ role: "engineer" }]);
  const ownerInvite = await invite("owner@example.com", "engineer");
  await asUser(owner, "select public.chisel_accept_invitation($1)", [ownerInvite.token]);
  assert.deepEqual(await asUser(owner, "select role from public.chisel_members where workspace_id=$1 and user_id=$2", [workspace, owner]), [{ role: "owner" }]);
  const pmInvite = await invite("pm@example.com", "pm");
  await asUser(pm, "select public.chisel_accept_invitation($1)", [pmInvite.token]);
});

test("members save canonical revisions with immutable snapshots and no inherited approval", async () => {
  const created = await save(owner, briefId, 0, workspace, { id: "spoof", revision: 900, updatedAt: "yesterday", checkedIds: ["AC-1"], note: "Feature" });
  assert.equal(created.id, briefId);
  assert.equal(created.revision, 1);
  assert.equal(created.updated_by, owner);
  assert.equal(created.draft.id, briefId);
  assert.equal(created.draft.revision, 1);
  assert.deepEqual(created.draft.checkedIds, []);
  assert.equal(Date.parse(String(created.draft.updatedAt)), Date.parse(created.updated_at));
  const updated = await save(engineer, briefId, 1, workspace, { note: "Refined feature" });
  assert.equal(updated.revision, 2);
  assert.equal(updated.updated_by, engineer);
  const versions = await asUser(pm, "select revision, draft->>'note' as note, created_by from public.chisel_brief_versions where brief_id=$1 order by revision", [briefId]);
  assert.deepEqual(versions, [{ revision: 1, note: "Feature", created_by: owner }, { revision: 2, note: "Refined feature", created_by: engineer }]);
  assert.equal((await asUser(engineer, "select * from public.chisel_briefs")).length, 1);
  assert.deepEqual(await asUser(outsider, "select * from public.chisel_briefs"), []);
  assert.deepEqual(await asUser(outsider, "select * from public.chisel_brief_versions"), []);
});

test("optimistic revision checks reject stale updates and duplicate inserts without extra versions", async () => {
  await assert.rejects(save(engineer, briefId, 1), /revision_conflict/i);
  await assert.rejects(save(owner, briefId, 0), /revision_conflict/i);
  await assert.rejects(save(owner, "20000000-0000-4000-8000-000000000099", 1), /revision_conflict/i);
  const attempts = await Promise.allSettled([save(pm, briefId, 2, workspace, { note: "PM update" }), save(engineer, briefId, 2, workspace, { note: "Engineer update" })]);
  assert.equal(attempts.filter((attempt) => attempt.status === "fulfilled").length, 1);
  assert.equal(attempts.filter((attempt) => attempt.status === "rejected").length, 1);
  assert.equal((await asUser(owner, "select * from public.chisel_brief_versions where brief_id=$1", [briefId])).length, 3);
});

test("brief IDs cannot be moved across workspaces even by an owner of both", async () => {
  await assert.rejects(save(owner, briefId, 3, secondWorkspace), /forbidden/i);
  await assert.rejects(save(engineer, "20000000-0000-4000-8000-000000000003", 0, secondWorkspace), /forbidden/i);
  await assert.rejects(save(outsider, briefId, 3), /forbidden/i);
  assert.equal((await asUser(owner, "select workspace_id from public.chisel_briefs where id=$1", [briefId]))[0].workspace_id, workspace);
});

test("all direct mutations, including role promotion and snapshot changes, are denied", async () => {
  for (const user of [owner, engineer, outsider]) {
    for (const sql of [
      "update public.chisel_members set role='owner'",
      "delete from public.chisel_members",
      "insert into public.chisel_members(workspace_id,user_id,email,role) values (gen_random_uuid(),auth.uid(),'spoof@example.com','owner')",
      "insert into public.chisel_workspaces(name,created_by) values ('Bypass',auth.uid())",
      "update public.chisel_workspaces set name='Bypass'",
      "delete from public.chisel_workspaces",
      "update public.chisel_briefs set revision=999",
      "delete from public.chisel_briefs",
      "insert into public.chisel_briefs(id,workspace_id,draft,revision,updated_by) values (gen_random_uuid(),gen_random_uuid(),'{}',1,auth.uid())",
      "update public.chisel_brief_versions set draft='{}'::jsonb",
      "delete from public.chisel_brief_versions",
      "insert into public.chisel_brief_versions(brief_id,revision,draft,created_by) values (gen_random_uuid(),999,'{}',auth.uid())",
      "update public.chisel_invitations set role='owner'",
      "delete from public.chisel_invitations",
      "insert into public.chisel_invitations(workspace_id,email,role,token_hash,created_by) values (gen_random_uuid(),'spoof@example.com','owner','spoof',auth.uid())",
      "truncate public.chisel_brief_versions",
    ]) await assert.rejects(asUser(user, sql), /permission denied/i);
  }
});

test("invalid or oversized draft payloads cannot create records", async () => {
  for (const draft of [null, [], "text", { note: "a".repeat(262145) }]) {
    await assert.rejects(save(owner, "20000000-0000-4000-8000-000000000090", 0, workspace, draft), /invalid/i);
  }
  await assert.rejects(save(owner, briefId, -1), /invalid/i);
  await assert.rejects(asUser(owner, "select public.chisel_save_brief($1,$2,null,'{}')", [workspace, briefId]), /invalid/i);
  await assert.rejects(asUser(owner, "select public.chisel_save_brief($1,null,0,'{}')", [workspace]), /invalid/i);
  assert.deepEqual(await asUser(owner, "select * from public.chisel_briefs where id='20000000-0000-4000-8000-000000000090'"), []);
});

test("only owners remove members; removal immediately revokes reads/writes and preserves history", async () => {
  await assert.rejects(asUser(engineer, "select public.chisel_remove_member($1,$2)", [workspace, pm]), /forbidden/i);
  await assert.rejects(asUser(owner, "select public.chisel_remove_member($1,$2)", [workspace, owner]), /owner|forbidden/i);
  const outstanding = await invite("engineer@example.com");
  await asUser(owner, "select public.chisel_remove_member($1,$2)", [workspace, engineer]);
  for (const table of ["chisel_workspaces", "chisel_members", "chisel_briefs", "chisel_brief_versions", "chisel_invitations"]) {
    assert.deepEqual(await asUser(engineer, `select * from public.${table}`), []);
  }
  await assert.rejects(save(engineer, briefId, 3), /forbidden/i);
  await assert.rejects(asUser(engineer, "select public.chisel_accept_invitation($1)", [outstanding.token]), /invitation/i);
  assert.equal((await asUser(owner, "select * from public.chisel_brief_versions where brief_id=$1", [briefId])).length, 3);
});

test("direct RPC validates editable draft shapes so malformed rows cannot poison team reads", async () => {
  const valid = validDraft();
  const story = { id: "US-1", persona: "", goal: "", benefit: "" };
  const malformed: unknown[] = [
    {}, { ...valid, note: 1 }, { ...valid, source: "spoof" }, { ...valid, model: 1 },
    { ...valid, model: "x".repeat(101) }, { ...valid, note: "x".repeat(12001) },
    { ...valid, generatedAt: "2026-02-30T12:00:00Z" }, { ...valid, generatedAt: "2026-10-06T12:00:00+00:00" },
    { ...valid, spec: {} }, { ...valid, spec: { ...valid.spec, title: "x".repeat(161) } },
    { ...valid, spec: { ...valid.spec, title: "😀".repeat(81) } },
    { ...valid, spec: { ...valid.spec, problem: null } }, { ...valid, spec: { ...valid.spec, inScope: "x" } },
    { ...valid, spec: { ...valid.spec, risks: [1] } }, { ...valid, spec: { ...valid.spec, risks: Array(31).fill("") } },
    { ...valid, spec: { ...valid.spec, extra: true } },
    { ...valid, spec: { ...valid.spec, userStories: [{ ...story, id: "bad id" }] } },
    { ...valid, spec: { ...valid.spec, userStories: [story, { ...story, id: " US-1 " }] } },
    { ...valid, spec: { ...valid.spec, userStories: [{ ...story, extra: true }] } },
    { ...valid, spec: { ...valid.spec, acceptanceCriteria: [{ id: "AC-1", given: "", when: "", then: false }] } },
  ];
  for (const draft of malformed) {
    await assert.rejects(asUser(owner, "select public.chisel_save_brief($1,$2,0,$3::jsonb)", [secondWorkspace, "20000000-0000-4000-8000-000000000091", JSON.stringify(draft)]), /invalid/i);
  }
  const incomplete = await save(owner, "20000000-0000-4000-8000-000000000092", 0, secondWorkspace, {
    ...valid, generatedAt: "2024-02-29T12:00:00Z",
    spec: { ...valid.spec, title: "😀".repeat(80), userStories: [story] },
  });
  assert.equal(draftSchema.parse(incomplete.draft).spec.problem, "");
});

test("pilot workspace and brief caps reject excess creates while allowing revisions", async () => {
  await asUser(owner, "select public.chisel_create_workspace('Third workspace')");
  await assert.rejects(asUser(owner, "select public.chisel_create_workspace('Fourth workspace')"), /limit_reached/i);
  for (let i = 2; i <= 25; i++) await save(owner, `30000000-0000-4000-8000-${String(i).padStart(12, "0")}`, 0);
  await assert.rejects(save(owner, "30000000-0000-4000-8000-000000000026", 0), /limit_reached/i);
  assert.equal((await save(owner, briefId, 3)).revision, 4);
});

test("pilot member cap counts the owner and leaves blocked invitations unconsumed", async () => {
  for (let i = 1; i <= 20; i++) {
    const user = `40000000-0000-4000-8000-${String(i).padStart(12, "0")}`;
    const email = `member${i}@example.com`;
    await db.query("insert into auth.users values ($1,$2,now())", [user, email]);
    const token = newToken();
    const invitation = await asUser(owner, "select public.chisel_create_invitation($1,$2,'engineer',$3) as id", [secondWorkspace, email, token]);
    if (i < 20) await asUser(user, "select public.chisel_accept_invitation($1)", [token]);
    else {
      await assert.rejects(asUser(user, "select public.chisel_accept_invitation($1)", [token]), /limit_reached/i);
      assert.equal((await asUser(owner, "select accepted_at from public.chisel_invitations where id=$1", [invitation[0].id]))[0].accepted_at, null);
      await asUser(owner, "select public.chisel_revoke_invitation($1)", [invitation[0].id]);
    }
  }
  const token = newToken();
  await asUser(owner, "select public.chisel_create_invitation($1,'owner@example.com','engineer',$2)", [secondWorkspace, token]);
  await asUser(owner, "select public.chisel_accept_invitation($1)", [token]);
  assert.equal((await asUser(owner, "select * from public.chisel_members where workspace_id=$1", [secondWorkspace])).length, 20);
});

test("pilot invitation cap counts only live unused invitations", async () => {
  const create = (i: number) => asUser(owner, "select public.chisel_create_invitation($1,$2,'pm',$3) as id", [secondWorkspace, `pending${i}@example.com`, newToken()]);
  const first = await create(1);
  for (let i = 2; i <= 25; i++) await create(i);
  await assert.rejects(create(26), /limit_reached/i);
  await asUser(owner, "select public.chisel_revoke_invitation($1)", [first[0].id]);
  const replacement = await create(26);
  await db.query("update public.chisel_invitations set expires_at=now()-interval '1 second' where id=$1", [replacement[0].id]);
  await create(27);
});

test("exposed RPC wrappers are invokers with restricted private definer implementations", async () => {
  const names = ["chisel_create_workspace", "chisel_create_invitation", "chisel_accept_invitation",
    "chisel_revoke_invitation", "chisel_remove_member", "chisel_save_brief"];
  const { rows } = await db.query<{
    schema: string; name: string; definer: boolean; authenticated: boolean; anonymous: boolean; public_execute: boolean; fixed_path: boolean;
  }>(`select n.nspname as schema, p.proname as name, p.prosecdef as definer,
      has_function_privilege('authenticated',p.oid,'EXECUTE') as authenticated,
      has_function_privilege('anon',p.oid,'EXECUTE') as anonymous,
      exists(select 1 from aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
        where a.grantee=0 and a.privilege_type='EXECUTE') as public_execute,
      'search_path=""'=any(p.proconfig) as fixed_path
    from pg_proc p join pg_namespace n on n.oid=p.pronamespace
    where n.nspname in ('public','chisel_private') and p.proname=any($1::text[])
    order by n.nspname,p.proname`, [names]);
  assert.equal(rows.length, 12, "six public wrappers must each have a private implementation");
  for (const row of rows) {
    assert.equal(row.definer, row.schema === "chisel_private", `${row.schema}.${row.name} security mode`);
    assert.equal(row.authenticated, true);
    assert.equal(row.anonymous, false);
    assert.equal(row.public_execute, false);
    assert.equal(row.fixed_path, true);
  }
  await assert.rejects(asUser(null, "select chisel_private.chisel_create_workspace('Bypass')"), /permission denied/i);
  await assert.rejects(asUser(outsider, "select chisel_private.chisel_save_brief($1,$2,4,$3::jsonb)", [workspace, briefId, JSON.stringify(validDraft())]), /forbidden/i);
  assert.equal((await db.query<{ can_execute: boolean }>("select has_function_privilege('authenticated','chisel_private.require_member(uuid,boolean)','EXECUTE') as can_execute")).rows[0].can_execute, false);
});

test("all Chisel foreign keys have supporting indexes", async () => {
  const { rows } = await db.query(`select c.conrelid::regclass::text as table_name, a.attname as column_name
    from pg_constraint c join pg_class t on t.oid=c.conrelid
    join pg_namespace n on n.oid=t.relnamespace
    join pg_attribute a on a.attrelid=c.conrelid and a.attnum=any(c.conkey)
    where c.contype='f' and n.nspname='public' and t.relname like 'chisel_%'
    and not exists(select 1 from pg_index i where i.indrelid=c.conrelid and i.indisvalid
      and i.indpred is null and i.indkey[0]=a.attnum)`);
  assert.deepEqual(rows, []);
});
