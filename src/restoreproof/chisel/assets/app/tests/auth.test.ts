import assert from "node:assert/strict";
import { test } from "node:test";
import { assertSameOrigin, privateJson, readJsonBody, RequestInputError, safeAuthNext } from "../lib/server/auth-request";
import { createAuthHandler, type AuthGateway } from "../lib/server/auth-controller";
import { readSupabaseConfig } from "../lib/supabase/config";

const origin = "http://localhost:3100";
const request = (body: unknown, extra: Record<string, string> = {}) => new Request(`${origin}/api/auth/send-code`, {
  method: "POST", headers: { origin, "content-type": "application/json", ...extra }, body: JSON.stringify(body),
});
const factory = (calls: string[]): (() => Promise<AuthGateway>) => async () => ({
  sendCode: async (email) => { calls.push(`send:${email}`); },
  verifyCode: async (email, token) => { calls.push(`verify:${email}:${token}`); },
  signOut: async () => { calls.push("signout"); },
});
const options = { appUrl: origin, production: false };

test("rejects cross-site and missing-origin mutations before contacting auth", async () => {
  const calls: string[] = [];
  const handler = createAuthHandler("send-code", factory(calls), options);
  assert.equal((await handler(request({ email: "pm@example.com" }, { origin: "https://attacker.example" }))).status, 403);
  const missing = request({ email: "pm@example.com" }); missing.headers.delete("origin");
  assert.equal((await handler(missing)).status, 403);
  assert.deepEqual(calls, []);
});
test("requires a configured production origin and rejects malformed origins", () => {
  assert.throws(() => assertSameOrigin(request({}), { production: true }), (e) => e instanceof RequestInputError && e.status === 503);
  assert.throws(() => assertSameOrigin(request({}), { appUrl: "not a URL", production: true }), RequestInputError);
  assert.throws(() => assertSameOrigin(request({}, { origin: `${origin}/fake` }), options), RequestInputError);
});
test("accepts the real loopback Host when Next normalizes the dev URL to localhost", async () => {
  const normalized = new Request("http://localhost:3100/api/auth/send-code", {
    method: "POST", headers: { host: "127.0.0.1:3100", origin: "http://127.0.0.1:3100", "content-type": "application/json" },
    body: JSON.stringify({ email: "pm@example.com" }),
  });
  assert.equal((await createAuthHandler("send-code", null, { production: false })(normalized)).status, 503);
});
test("dev Host fallback does not accept remote hosts, wrong ports or forwarded hosts", () => {
  const cases: Record<string, string>[] = [
    { host: "evil.example:3100", origin: "http://evil.example:3100" },
    { host: "127.0.0.1:3101", origin: "http://127.0.0.1:3101" },
    { host: "localhost:3100", origin: "http://evil.example:3100", "x-forwarded-host": "evil.example:3100" },
    { host: "127.0.0.1:3100@evil.example", origin: "http://evil.example" },
  ];
  for (const headers of cases) {
    const normalized = new Request("http://localhost:3100/api/auth/send-code", { method: "POST", headers });
    assert.throws(() => assertSameOrigin(normalized, { production: false }), (e) => e instanceof RequestInputError && e.status === 403);
  }
});
test("configured origin stays strict even when the dev Host is a different loopback address", () => {
  const normalized = new Request("http://localhost:3100/api/auth/send-code", {
    method: "POST", headers: { host: "127.0.0.1:3100", origin: "http://127.0.0.1:3100" },
  });
  assert.throws(() => assertSameOrigin(normalized, options), (e) => e instanceof RequestInputError && e.status === 403);
  assert.throws(() => assertSameOrigin(normalized, { appUrl: origin, production: true }), (e) => e instanceof RequestInputError && e.status === 403);
});
test("caps streamed request bytes even without a Content-Length", async () => {
  await assert.rejects(readJsonBody(request({ email: "x".repeat(200) }), 64), (e) => e instanceof RequestInputError && e.status === 413);
  await assert.rejects(readJsonBody(request({}, { "content-type": "text/plain" })), (e) => e instanceof RequestInputError && e.status === 415);
});
test("invalid email and unknown auth fields have no provider effect", async () => {
  const calls: string[] = [];
  const handler = createAuthHandler("send-code", factory(calls), options);
  assert.equal((await handler(request({ email: "bad" }))).status, 400);
  assert.equal((await handler(request({ email: "pm@example.com", role: "owner" }))).status, 400);
  assert.deepEqual(calls, []);
});
test("sends one normalized email OTP request with a private response", async () => {
  const calls: string[] = [];
  const response = await createAuthHandler("send-code", factory(calls), options)(request({ email: " PM@example.com " }));
  assert.equal(response.status, 200);
  assert.deepEqual(calls, ["send:pm@example.com"]);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
});
test("verifies numeric OTP before reporting sign-in success", async () => {
  const calls: string[] = [];
  const handler = createAuthHandler("verify-code", factory(calls), options);
  assert.equal((await handler(request({ email: "pm@example.com", token: "ABCDEF" }))).status, 400);
  assert.equal((await handler(request({ email: "pm@example.com", token: "123456" }))).status, 200);
  assert.deepEqual(calls, ["verify:pm@example.com:123456"]);
});
test("unconfigured auth never calls the provider", async () => {
  const response = await createAuthHandler("send-code", null, options)(request({ email: "pm@example.com" }));
  assert.equal(response.status, 503);
});
test("provider errors do not expose secrets or account state", async () => {
  const gateway = factory([]);
  const failing = async () => ({ ...await gateway(), sendCode: async () => { throw new Error("secret-token user already exists"); } });
  const response = await createAuthHandler("send-code", failing, options)(request({ email: "pm@example.com" }));
  assert.equal(response.status, 502);
  assert.doesNotMatch(await response.text(), /secret-token|already exists/);
});
test("signout is a same-origin request without an input body", async () => {
  const calls: string[] = [];
  const response = await createAuthHandler("signout", factory(calls), options)(new Request(`${origin}/api/auth/signout`, { method: "POST", headers: { origin } }));
  assert.equal(response.status, 200);
  assert.deepEqual(calls, ["signout"]);
});
test("login return paths cannot redirect outside the team workflow", () => {
  const invite = `/join/${"a".repeat(64)}`;
  assert.equal(safeAuthNext(invite), invite);
  assert.equal(safeAuthNext("/team"), "/team");
  for (const value of ["//evil.example", "https://evil.example", "/\\evil.example", "/team?next=//evil.example", "/join/invalid", undefined]) {
    assert.equal(safeAuthNext(value), "/team");
  }
});
test("config rejects secret keys, missing values, and malformed project URLs", () => {
  assert.equal(readSupabaseConfig(undefined, undefined), null);
  assert.equal(readSupabaseConfig("https://project.supabase.co", "sb_secret_private"), null);
  assert.equal(readSupabaseConfig("https://user:pass@project.supabase.co", "sb_publishable_public"), null);
  assert.equal(readSupabaseConfig("not a URL", "sb_publishable_public"), null);
  assert.deepEqual(readSupabaseConfig("https://project.supabase.co/", "sb_publishable_public"), { url: "https://project.supabase.co", publishableKey: "sb_publishable_public" });
});
test("all auth JSON responses prohibit caching", () => {
  assert.equal(privateJson({ error: "invalid" }, 400).headers.get("cache-control"), "private, no-store");
});
