import type { FeatureDraft } from "../../lib/local-drafts";

export type TeamEditorState = { draft: FeatureDraft | null; dirty: boolean; conflict: boolean };
export type TeamEditorEvent =
  | { type: "open" | "saved" | "change"; draft: FeatureDraft }
  | { type: "clear" }
  | { type: "conflict" };
export const emptyEditor: TeamEditorState = { draft: null, dirty: false, conflict: false };

export const teamEditorReducer = (state: TeamEditorState, event: TeamEditorEvent): TeamEditorState => {
  if (event.type === "clear") return emptyEditor;
  if (event.type === "conflict") return { ...state, conflict: true };
  if (event.type === "change") return { ...state, draft: event.draft, dirty: true };
  return { draft: structuredClone(event.draft), dirty: false, conflict: false };
};

export const copyToTeam = (draft: FeatureDraft, id: string, updatedAt: string): FeatureDraft => ({
  ...structuredClone(draft), id, updatedAt, revision: 0, checkedIds: [],
});
