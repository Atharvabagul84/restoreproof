import assert from "node:assert/strict";
import test from "node:test";
import { manualFeature } from "../lib/example-feature";
import type { FeatureDraft } from "../lib/local-drafts";
import { emptyEditor, teamEditorReducer, copyToTeam } from "../components/team/editor-state";

const draft: FeatureDraft = { id: "f1", spec: manualFeature(), note: "Original customer notes", source: "manual", model: null, generatedAt: null, updatedAt: "2026-10-06T00:00:00.000Z", revision: 3, checkedIds: ["AC-001"] };

test("conflicting save retains every local edit and its original base revision", () => {
  const opened = teamEditorReducer(emptyEditor, { type: "open", draft });
  const edited = teamEditorReducer(opened, { type: "change", draft: { ...draft, spec: { ...draft.spec, title: "My edits" } } });
  const failed = teamEditorReducer(edited, { type: "conflict" });
  assert.equal(failed.draft?.spec.title, "My edits");
  assert.equal(failed.draft?.note, draft.note);
  assert.equal(failed.draft?.revision, 3);
  assert.equal(failed.dirty, true);
  assert.equal(failed.conflict, true);
});

test("a saved shared revision clears dirty and conflict state without inventing review marks", () => {
  const state = teamEditorReducer({ draft, dirty: true, conflict: true }, { type: "saved", draft: { ...draft, revision: 4, checkedIds: [] } });
  assert.equal(state.draft?.revision, 4);
  assert.deepEqual(state.draft?.checkedIds, []);
  assert.equal(state.dirty, false);
  assert.equal(state.conflict, false);
});

test("explicitly bringing a browser draft creates a separate shared draft and preserves its source", () => {
  const copied = copyToTeam(draft, "new-id", "2026-10-06T01:00:00.000Z");
  assert.equal(copied.id, "new-id");
  assert.equal(copied.revision, 0);
  assert.deepEqual(copied.checkedIds, []);
  assert.equal(copied.note, draft.note);
  copied.spec.title = "Shared copy";
  assert.equal(draft.spec.title, "Untitled feature");
  assert.equal(draft.revision, 3);
});
