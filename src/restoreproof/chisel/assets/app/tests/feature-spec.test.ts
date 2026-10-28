import assert from "node:assert/strict";
import test from "node:test";
import { featureSpecSchema, generateRequestSchema } from "../lib/feature-spec";
import { sampleFeatureSpec } from "./fixtures/feature-spec";

test("validates and trims a complete feature specification", () => {
  const parsed = featureSpecSchema.parse({ ...sampleFeatureSpec, title: "  Team ownership  " });
  assert.equal(parsed.title, "Team ownership");
});

test("rejects incomplete or unexpectedly shaped model output", () => {
  assert.equal(featureSpecSchema.safeParse({ title: "Only a title" }).success, false);
  assert.equal(featureSpecSchema.safeParse({ ...sampleFeatureSpec, inScope: [] }).success, false);
  assert.equal(featureSpecSchema.safeParse({ ...sampleFeatureSpec, inventedApproval: true }).success, false);
  assert.equal(featureSpecSchema.safeParse({ ...sampleFeatureSpec, risks: [" "] }).success, false);
});

test("rejects duplicate acceptance criterion identifiers", () => {
  assert.equal(featureSpecSchema.safeParse({
    ...sampleFeatureSpec,
    acceptanceCriteria: [sampleFeatureSpec.acceptanceCriteria[0], sampleFeatureSpec.acceptanceCriteria[0]],
  }).success, false);
});

test("limits output size and collection length", () => {
  assert.equal(featureSpecSchema.safeParse({ ...sampleFeatureSpec, title: "x".repeat(161) }).success, false);
  assert.equal(featureSpecSchema.safeParse({ ...sampleFeatureSpec, risks: Array(31).fill("Risk") }).success, false);
});

test("requires a trimmed note of 30 to 12000 characters and no extra parameters", () => {
  assert.equal(generateRequestSchema.parse({ note: `  ${"a".repeat(30)}  ` }).note.length, 30);
  for (const note of [undefined, null, 25, {}, " ".repeat(40), "a".repeat(29), "a".repeat(12001)]) {
    assert.equal(generateRequestSchema.safeParse({ note }).success, false);
  }
  assert.equal(generateRequestSchema.safeParse({ note: "a".repeat(30), apiKey: "secret" }).success, false);
});
