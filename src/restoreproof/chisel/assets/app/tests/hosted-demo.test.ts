import assert from "node:assert/strict";
import test from "node:test";
import { createGenerateSpecHandler } from "../lib/server/generate-spec-controller";
import { generateFeatureSpec, GenerationError } from "../lib/server/feature-spec-generation";
import { createLimiter, LimiterUnavailableError, visitorId, type GenerationLimiter } from "../lib/server/generation-rate-limit";
import { createGroqCompletion } from "../lib/server/groq-feature-spec";
import { sampleFeatureSpec } from "./fixtures/feature-spec";

const note = "Let engineering managers assign owners to incoming tasks.";
const appUrl = "https://chisel.example";
const demoConfig = { provider: "groq" as const, apiKey: "test-key", model: "openai/gpt-oss-120b", production: true, hostedDemo: true };
const origin = { appUrl, production: true };
const succeed = async () => ({ text: JSON.stringify(sampleFeatureSpec), stopReason: "end_turn" });
const allowAll: GenerationLimiter = async () => ({ allowed: true, remaining: 2 });
const makeRequest = (headers: Record<string, string> = {}) => new Request(`${appUrl}/api/generate-prd`, {
  method: "POST",
  headers: { "content-type": "application/json", origin: appUrl, "x-forwarded-for": "203.0.113.7", ...headers },
  body: JSON.stringify({ note }),
});

const groqResponse = (body: unknown, status = 200) => async () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const groqChoice = (content: string | null, finish_reason: string) => ({ choices: [{ message: { content }, finish_reason }] });

test("Groq adapter sends a JSON-mode chat request and maps a clean finish", async () => {
  let sent: { url: string; init: RequestInit } | undefined;
  const complete = createGroqCompletion("secret", async (url, init) => {
    sent = { url: String(url), init: init! };
    return groqResponse(groqChoice(JSON.stringify(sampleFeatureSpec), "stop"))();
  });
  const result = await generateFeatureSpec(note, { model: "openai/gpt-oss-120b", complete });
  assert.deepEqual(result.spec, sampleFeatureSpec);
  assert.equal(sent?.url, "https://api.groq.com/openai/v1/chat/completions");
  assert.equal(new Headers(sent?.init.headers).get("authorization"), "Bearer secret");
  const body = JSON.parse(String(sent?.init.body));
  assert.equal(body.model, "openai/gpt-oss-120b");
  assert.deepEqual(body.response_format, { type: "json_object" });
  assert.deepEqual(body.messages.map((message: { role: string }) => message.role), ["system", "user"]);
});

test("Groq adapter treats a length cut-off as an incomplete spec", async () => {
  const complete = createGroqCompletion("secret", groqResponse(groqChoice(JSON.stringify(sampleFeatureSpec), "length")));
  await assert.rejects(generateFeatureSpec(note, { model: "m", complete }),
    (error: unknown) => error instanceof GenerationError && error.code === "invalid_output");
});

test("Groq HTTP failures become safe, visible errors", async () => {
  for (const [status, code] of [[429, "provider_busy"], [401, "generation_unavailable"], [500, "generation_failed"]] as const) {
    const complete = createGroqCompletion("secret", groqResponse({ error: { message: `echo ${note}` } }, status));
    await assert.rejects(generateFeatureSpec(note, { model: "m", complete }),
      (error: unknown) => error instanceof GenerationError && error.code === code && !error.message.includes(note));
  }
});

test("limiter checks the visitor before the shared budget", async () => {
  const calls: string[] = [];
  const limit = createLimiter({
    visitor: async (id) => { calls.push(`visitor:${id}`); return { success: false, remaining: 0, reset: 1 }; },
    global: async (id) => { calls.push(`global:${id}`); return { success: true, remaining: 99, reset: 1 }; },
  });
  assert.deepEqual(await limit("v1"), { allowed: false, scope: "visitor", reset: 1 });
  assert.deepEqual(calls, ["visitor:v1"]);
});

test("limiter reports the shared limit and the visitor's remaining drafts", async () => {
  const ok = { success: true, remaining: 1, reset: 5 };
  assert.deepEqual(await createLimiter({ visitor: async () => ok, global: async () => ({ ...ok, success: false }) })("v"), { allowed: false, scope: "global", reset: 5 });
  assert.deepEqual(await createLimiter({ visitor: async () => ok, global: async () => ({ ...ok, remaining: 50 }) })("v"), { allowed: true, remaining: 1 });
});

test("limiter fails closed on store errors and on Upstash's fail-open timeout", async () => {
  const ok = { success: true, remaining: 1, reset: 5 };
  await assert.rejects(createLimiter({ visitor: async () => { throw new Error("down"); }, global: async () => ok })("v"), LimiterUnavailableError);
  await assert.rejects(createLimiter({ visitor: async () => ({ ...ok, reason: "timeout" }), global: async () => ok })("v"), LimiterUnavailableError);
});

test("visitor IDs are salted hashes, never the raw address", () => {
  const id = visitorId(makeRequest(), "salt");
  assert.match(id, /^[a-f0-9]{64}$/);
  assert.ok(!id.includes("203.0.113.7"));
  assert.notEqual(id, visitorId(makeRequest(), "other-salt"));
  assert.equal(id, visitorId(makeRequest({ "x-forwarded-for": "203.0.113.7, 10.0.0.1" }), "salt"));
});

test("hosted demo generates for an allowed visitor and reports remaining drafts", async () => {
  const handler = createGenerateSpecHandler({ config: demoConfig, complete: succeed, limiter: { limit: allowAll, salt: "s" }, origin });
  const response = await handler(makeRequest());
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("ratelimit-remaining"), "2");
  assert.deepEqual((await response.json()).spec, sampleFeatureSpec);
});

test("hosted demo stays closed without a limiter, even with a key", async () => {
  let called = false;
  const handler = createGenerateSpecHandler({ config: demoConfig, complete: async () => { called = true; return succeed(); }, limiter: null, origin });
  const response = await handler(makeRequest());
  assert.equal(response.status, 503);
  assert.equal((await response.json()).code, "generation_unavailable");
  assert.equal(called, false);
});

test("hosted demo returns 429 with Retry-After once a visitor is over the limit", async () => {
  let called = false;
  const limit: GenerationLimiter = async () => ({ allowed: false, scope: "visitor", reset: Date.now() + 3_600_000 });
  const handler = createGenerateSpecHandler({ config: demoConfig, complete: async () => { called = true; return succeed(); }, limiter: { limit, salt: "s" }, origin });
  const response = await handler(makeRequest());
  assert.equal(response.status, 429);
  assert.equal((await response.json()).code, "rate_limited");
  assert.ok(Number(response.headers.get("retry-after")) > 3000);
  assert.equal(called, false);
});

test("hosted demo pauses when limits can't be checked", async () => {
  const limit: GenerationLimiter = async () => { throw new LimiterUnavailableError(); };
  const handler = createGenerateSpecHandler({ config: demoConfig, complete: succeed, limiter: { limit, salt: "s" }, origin });
  assert.equal((await handler(makeRequest())).status, 503);
});

test("hosted demo rejects cross-site requests before spending a draft", async () => {
  let limited = false;
  const limit: GenerationLimiter = async () => { limited = true; return { allowed: true, remaining: 2 }; };
  const handler = createGenerateSpecHandler({ config: demoConfig, complete: succeed, limiter: { limit, salt: "s" }, origin });
  const response = await handler(makeRequest({ origin: "https://evil.example" }));
  assert.equal(response.status, 403);
  assert.equal(limited, false);
});

test("missing Groq key names the right variable", async () => {
  const handler = createGenerateSpecHandler({ config: { ...demoConfig, apiKey: "" }, complete: succeed, limiter: { limit: allowAll, salt: "s" }, origin });
  assert.match((await (await handler(makeRequest())).json()).error, /GROQ_API_KEY/);
});
