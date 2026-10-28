import assert from "node:assert/strict";
import test from "node:test";
import { generateFeatureSpec, GenerationError, type CompletionRequest } from "../lib/server/feature-spec-generation";
import { sampleFeatureSpec } from "./fixtures/feature-spec";

const note = "Let engineering managers assign owners to incoming tasks.";

test("returns validated content with server model and timestamp provenance", async () => {
  let received: CompletionRequest | undefined;
  const result = await generateFeatureSpec(note, {
    model: "test-model",
    complete: async (request) => { received = request; return { text: JSON.stringify(sampleFeatureSpec), stopReason: "end_turn" }; },
  });
  assert.deepEqual(result.spec, sampleFeatureSpec);
  assert.equal(result.model, "test-model");
  assert.ok(Number.isFinite(Date.parse(result.generatedAt)));
  assert.equal(received?.note, note);
  assert.match(received?.system ?? "", /assumptions/i);
  assert.match(received?.system ?? "", /To be agreed/);
});

test("rejects malformed JSON, missing fields and truncated completions instead of using a sample", async () => {
  for (const response of [
    { text: "not json", stopReason: "end_turn" },
    { text: '{"title":"Incomplete"}', stopReason: "end_turn" },
    { text: JSON.stringify(sampleFeatureSpec), stopReason: "max_tokens" },
  ]) {
    await assert.rejects(generateFeatureSpec(note, { model: "test", complete: async () => response }),
      (error: unknown) => error instanceof GenerationError && error.code === "invalid_output" && error.status === 502);
  }
});

test("times out an unresponsive provider and aborts its request", async () => {
  let signal: AbortSignal | undefined;
  await assert.rejects(generateFeatureSpec(note, {
    model: "test", timeoutMs: 10,
    complete: (request) => { signal = request.signal; return new Promise(() => {}); },
  }), (error: unknown) => error instanceof GenerationError && error.code === "generation_timeout" && error.status === 504);
  assert.equal(signal?.aborted, true);
});

test("cancels generation when the caller aborts", async () => {
  const controller = new AbortController();
  const pending = generateFeatureSpec(note, {
    model: "test", signal: controller.signal,
    complete: async () => new Promise(() => {}),
  });
  controller.abort();
  await assert.rejects(pending, (error: unknown) => error instanceof GenerationError && error.code === "generation_cancelled");
});

test("does not start provider work for an already cancelled request", async () => {
  const controller = new AbortController();
  controller.abort();
  let called = false;
  await assert.rejects(generateFeatureSpec(note, {
    model: "test", signal: controller.signal,
    complete: async () => { called = true; return { text: JSON.stringify(sampleFeatureSpec), stopReason: "end_turn" }; },
  }), (error: unknown) => error instanceof GenerationError && error.code === "generation_cancelled");
  assert.equal(called, false);
});

test("does not expose provider messages or secrets to the client", async () => {
  await assert.rejects(generateFeatureSpec(note, {
    model: "test", complete: async () => { throw Object.assign(new Error("secret provider detail"), { status: 429 }); },
  }), (error: unknown) => error instanceof GenerationError && error.status === 503 && !error.message.includes("secret"));
});
