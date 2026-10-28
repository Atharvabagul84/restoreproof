import assert from "node:assert/strict";
import test from "node:test";
import { createGenerateSpecHandler } from "../lib/server/generate-spec-controller";
import { sampleFeatureSpec } from "./fixtures/feature-spec";

const note = "Let engineering managers assign owners to incoming tasks.";
const developmentConfig = { apiKey: "test-key", model: "test-model", production: false };
const makeRequest = (body: string, headers: Record<string, string> = { "content-type": "application/json" }) =>
  new Request("http://localhost/api/generate-prd", { method: "POST", headers, body });

test("returns the generated spec without mock or legacy response fields", async () => {
  const handler = createGenerateSpecHandler({
    config: developmentConfig,
    complete: async () => ({ text: JSON.stringify(sampleFeatureSpec), stopReason: "end_turn" }),
  });
  const response = await handler(makeRequest(JSON.stringify({ note })));
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.deepEqual(body.spec, sampleFeatureSpec);
  assert.deepEqual(Object.keys(body).sort(), ["generatedAt", "model", "spec"]);
  assert.match(response.headers.get("cache-control") ?? "", /no-store/);
});

test("rejects malformed input before invoking the provider", async () => {
  let calls = 0;
  const handler = createGenerateSpecHandler({ config: developmentConfig, complete: async () => { calls++; throw new Error("unexpected"); } });
  for (const body of ["{", "null", JSON.stringify({ note: 15 }), JSON.stringify({ note: "short" })]) {
    assert.equal((await handler(makeRequest(body))).status, 400);
  }
  assert.equal((await handler(makeRequest(JSON.stringify({ note }), { "content-type": "text/plain" }))).status, 415);
  assert.equal((await handler(makeRequest(JSON.stringify({ note: "x".repeat(70_000) })))).status, 413);
  assert.equal(calls, 0);
});

test("counts bytes of streamed bodies instead of trusting content-length", async () => {
  const handler = createGenerateSpecHandler({ config: developmentConfig, complete: async () => { throw new Error("unexpected"); } });
  const request = makeRequest(JSON.stringify({ note: "x".repeat(70_000) }), { "content-type": "application/json", "content-length": "2" });
  assert.equal((await handler(request)).status, 413);
});

test("fails clearly when no provider key is configured", async () => {
  const handler = createGenerateSpecHandler({ config: { ...developmentConfig, apiKey: "" }, complete: async () => { throw new Error("unexpected"); } });
  const response = await handler(makeRequest(JSON.stringify({ note })));
  assert.equal(response.status, 503);
  assert.equal((await response.json()).code, "generation_unavailable");
});

test("disables unauthenticated production generation even when a key is configured", async () => {
  let called = false;
  const handler = createGenerateSpecHandler({ config: { ...developmentConfig, production: true }, complete: async () => { called = true; throw new Error("unexpected"); } });
  assert.equal((await handler(makeRequest(JSON.stringify({ note })))).status, 503);
  assert.equal(called, false);
});

test("returns a safe upstream failure instead of a fake document", async () => {
  const handler = createGenerateSpecHandler({ config: developmentConfig, complete: async () => ({ text: "invalid JSON", stopReason: "end_turn" }) });
  const response = await handler(makeRequest(JSON.stringify({ note })));
  assert.equal(response.status, 502);
  const body = await response.json();
  assert.equal(body.code, "invalid_output");
  assert.equal(body.spec, undefined);
});
