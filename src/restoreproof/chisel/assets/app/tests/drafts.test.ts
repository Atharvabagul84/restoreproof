import assert from "node:assert/strict";
import test from "node:test";
import { draftToMarkdown, parseDrafts, saveDraft } from "../lib/local-drafts";

const draft = {
  id: "draft-one", note: "Allow support leads to export filtered tickets to CSV.",
  source: "example" as const, model: null, generatedAt: null,
  updatedAt: "2026-10-06T09:00:00.000Z", revision: 1, checkedIds: ["AC-1"],
  spec: {
    title: "Ticket export", problem: "Support leads cannot take ticket data into reports.",
    targetUser: "Support lead", successMetric: "To be agreed",
    inScope: ["CSV export of filtered tickets"], outOfScope: ["Scheduled exports"],
    userStories: [{ id: "US-1", persona: "Support lead", goal: "Export filtered tickets", benefit: "Prepare a report" }],
    acceptanceCriteria: [
      { id: "AC-1", given: "a filtered list", when: "I export", then: "the CSV contains only matching tickets" },
      { id: "AC-2", given: "an empty result", when: "I export", then: "the file contains column headers" },
    ],
    assumptions: ["CSV is sufficient"], openQuestions: ["Which fields may be exported?"], risks: ["Exports may contain personal data"],
  },
};

test("export preserves the edited spec, provenance and actual review selections", () => {
  const markdown = draftToMarkdown(draft);
  assert.match(markdown, /Ticket export/);
  assert.match(markdown, /Which fields may be exported/);
  assert.match(markdown, /\[x\].*AC-1/);
  assert.match(markdown, /\[ \].*AC-2/);
  assert.match(markdown, /Example/);
  assert.match(markdown, /not.*test/i);
  assert.doesNotMatch(markdown, /99\.4|250ms|GitHub triage|Approved by/);
});

test("saving a revision replaces only that draft and retains other drafts", () => {
  const other = { ...draft, id: "draft-two" };
  const saved = saveDraft([draft, other], { ...draft, spec: { ...draft.spec, title: "Updated export" } });
  assert.equal(saved.length, 2);
  assert.equal(saved[0].revision, 2);
  assert.equal(saved[0].spec.title, "Updated export");
  assert.equal(saved[1].id, "draft-two");
});

test("storage validation rejects corrupt data instead of dropping drafts silently", () => {
  assert.throws(() => parseDrafts("not json"));
  assert.throws(() => parseDrafts(JSON.stringify([{ ...draft, spec: { title: "partial" } }])));
});

test("saved drafts round-trip their source note and schema", () => {
  const restored = parseDrafts(JSON.stringify([draft]));
  assert.equal(restored[0].note, draft.note);
  assert.deepEqual(restored[0].spec, draft.spec);
});

test("an unfinished edit can be saved and reopened without losing work", () => {
  const partial = { ...draft, spec: { ...draft.spec, title: "", problem: "", inScope: [], userStories: [{ id: "US-1", persona: "", goal: "", benefit: "" }] } };
  const saved = saveDraft([], partial);
  assert.equal(parseDrafts(JSON.stringify(saved))[0].spec.problem, "");
});

test("a new draft export is never described as a saved revision", () => {
  const markdown = draftToMarkdown({ ...draft, revision: 0 });
  assert.match(markdown, /not saved yet/i);
  assert.doesNotMatch(markdown, /Saved revision 0/);
});

test("a stale tab cannot overwrite a newer saved revision", () => {
  assert.throws(() => saveDraft([{ ...draft, revision: 2 }], draft), /newer revision/i);
});

test("multiline acceptance text stays nested in the exported checklist", () => {
  const multiline = { ...draft, spec: { ...draft.spec, acceptanceCriteria: [{ ...draft.spec.acceptanceCriteria[0], then: "first outcome\nsecond outcome" }] } };
  assert.match(draftToMarkdown(multiline), /Then first outcome\n    second outcome/);
});
