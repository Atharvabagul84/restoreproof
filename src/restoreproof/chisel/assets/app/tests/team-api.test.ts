import assert from "node:assert/strict";
import { test } from "node:test";
import { createTeamHandler, type TeamRepository } from "../lib/server/team-controller";
import { RequestInputError } from "../lib/server/auth-request";
import { EXAMPLE_SPEC } from "../lib/example-feature";

const id = "10000000-0000-4000-8000-000000000001";
const request = (body: unknown, origin = "http://localhost:3100") => new Request(`${origin}/api/team/workspaces`, {
  method: "POST", headers: { origin, "content-type": "application/json" }, body: JSON.stringify(body),
});
const config = { production: false };
const draft = { id, note: "Original user evidence", spec: EXAMPLE_SPEC, source: "manual", model: null, generatedAt: null, updatedAt: new Date().toISOString(), revision: 0, checkedIds: [] };
const makeRepository = () => {
  const writes: unknown[] = [];
  const repository: TeamRepository = {
    listWorkspaces: async () => [], getWorkspace: async () => { throw new Error("unused"); },
    createWorkspace: async (name) => { writes.push(name); return id; },
    saveBrief: async (workspaceId, input) => { writes.push({ workspaceId, input }); return { id, workspaceId, draft: input.draft, revision: 1, updatedAt: draft.updatedAt, updatedBy: id }; },
    createInvitation: async (_workspaceId, email, role, token) => { writes.push({ email, role, token }); return id; },
    acceptInvitation: async () => id, revokeInvitation: async () => {}, removeMember: async () => {},
  };
  return { repository, writes };
};
test("unconfigured and unauthenticated workspaces fail closed", async () => {
  assert.equal((await createTeamHandler("list", null, config)(new Request("http://localhost:3100/api/team/workspaces"))).status, 503);
  const response = await createTeamHandler("create", async () => { throw new RequestInputError(401, "Sign in first."); }, config)(request({ name: "Design" }));
  assert.equal(response.status, 401);
});
test("cross-origin mutations cannot reach the repository", async () => {
  const { repository, writes } = makeRepository();
  const response = await createTeamHandler("create", async () => repository, config)(new Request("http://localhost:3100/api/team/workspaces", { method: "POST", headers: { origin: "https://evil.example", "content-type": "application/json" }, body: '{"name":"hijack"}' }));
  assert.equal(response.status, 403); assert.deepEqual(writes, []);
});
test("workspace creation trims input and returns private responses", async () => {
  const { repository, writes } = makeRepository();
  const response = await createTeamHandler("create", async () => repository, config)(request({ name: " Delivery " }));
  assert.equal(response.status, 201); assert.deepEqual(await response.json(), { id });
  assert.deepEqual(writes, ["Delivery"]); assert.match(response.headers.get("cache-control")!, /no-store/);
});
test("owner roles and client invite tokens cannot be injected", async () => {
  const { repository, writes } = makeRepository();
  for (const body of [{ email: "pm@example.com", role: "owner" }, { email: "pm@example.com", role: "pm", token: "guessable" }]) {
    assert.equal((await createTeamHandler("invite", async () => repository, config)(request(body), { workspaceId: id })).status, 400);
  }
  assert.deepEqual(writes, []);
});
test("invitations get unpredictable tokens and normalize email", async () => {
  const { repository, writes } = makeRepository();
  const handler = createTeamHandler("invite", async () => repository, config);
  const first = await (await handler(request({ email: " PM@Example.com ", role: "pm" }), { workspaceId: id })).json();
  const second = await (await handler(request({ email: "pm@example.com", role: "pm" }), { workspaceId: id })).json();
  assert.match(first.invitePath, /^\/join\/[a-f0-9]{64}$/); assert.notEqual(first.invitePath, second.invitePath);
  assert.equal((writes[0] as {email:string}).email, "pm@example.com");
});
test("save accepts incomplete drafts but rejects invalid revision or identifiers", async () => {
  const { repository, writes } = makeRepository();
  const handler = createTeamHandler("save", async () => repository, config);
  assert.equal((await handler(request({ draft: { ...draft, spec: { ...draft.spec, title: "" } }, expectedRevision: 0 }), { workspaceId: id })).status, 200);
  assert.equal((await handler(request({ draft, expectedRevision: -1 }), { workspaceId: id })).status, 400);
  assert.equal((await handler(request({ draft, expectedRevision: 0 }), { workspaceId: "wrong" })).status, 400);
  assert.equal(writes.length, 1);
});
test("stale revisions become actionable conflicts without leaking database details", async () => {
  const { repository } = makeRepository();
  repository.saveBrief = async () => { throw { code: "40001", message: "private SQL detail" }; };
  const response = await createTeamHandler("save", async () => repository, config)(request({ draft, expectedRevision: 1 }), { workspaceId: id });
  assert.equal(response.status, 409); assert.match((await response.json()).error, /newer revision/i);
});
test("oversized requests are rejected before storing data", async () => {
  const { repository, writes } = makeRepository();
  const response = await createTeamHandler("create", async () => repository, config)(request({ name: "x".repeat(270000) }));
  assert.equal(response.status, 413); assert.deepEqual(writes, []);
});
test("database pilot limits return a useful message without leaking the raw error", async () => {
  const { repository } = makeRepository();
  repository.createWorkspace = async () => { throw { code: "22023", message: "CHISEL_LIMIT_REACHED: private SQL detail" }; };
  const response = await createTeamHandler("create", async () => repository, config)(request({ name: "Another team" }));
  assert.equal(response.status, 422);
  const { error } = await response.json();
  assert.match(error, /pilot limit/i); assert.doesNotMatch(error, /private SQL/);
});
