import { z } from "zod";
import { featureSpecSchema } from "./feature-spec";

export const DRAFT_STORAGE_KEY = "chisel.feature-drafts.v1";
const editableText = z.string().max(2000);
const editableList = z.array(editableText).max(30);
// Incomplete editor work must be saveable; stricter generation validation still
// governs model responses and Markdown handoffs.
const editableSpecSchema = featureSpecSchema.safeExtend({
  title: z.string().max(160), problem: editableText, targetUser: editableText, successMetric: editableText,
  inScope: editableList, outOfScope: editableList, assumptions: editableList, openQuestions: editableList, risks: editableList,
  userStories: z.array(featureSpecSchema.shape.userStories.element.extend({ persona: editableText, goal: editableText, benefit: editableText })).max(30),
  acceptanceCriteria: z.array(featureSpecSchema.shape.acceptanceCriteria.element.extend({ given: editableText, when: editableText, then: editableText })).max(30),
});
export const draftSchema = z.object({
  id: z.string().min(1).max(100),
  note: z.string().max(12000),
  spec: editableSpecSchema,
  source: z.enum(["example", "ai", "manual"]),
  model: z.string().max(100).nullable(),
  generatedAt: z.string().datetime().nullable(),
  updatedAt: z.string().datetime(),
  revision: z.number().int().min(0),
  checkedIds: z.array(z.string().max(100)).max(40),
});
export type FeatureDraft = z.infer<typeof draftSchema>;
export class DraftSaveError extends Error {}

export const parseDrafts = (raw: string): FeatureDraft[] => z.array(draftSchema).max(25).parse(JSON.parse(raw));

export const saveDraft = (drafts: FeatureDraft[], draft: FeatureDraft): FeatureDraft[] => {
  const existing = drafts.find((item) => item.id === draft.id);
  if (existing && existing.revision !== draft.revision) throw new DraftSaveError("A newer revision was saved in another tab. Export your edits, then reload and reopen the latest draft before saving.");
  if (!existing && drafts.length >= 25) throw new DraftSaveError("This browser holds 25 drafts. Export and remove a draft before adding another.");
  const saved = draftSchema.parse({ ...draft, revision: existing ? existing.revision + 1 : 1, updatedAt: new Date().toISOString() });
  return [saved, ...drafts.filter((item) => item.id !== draft.id)];
};

const indentLines = (text: string, spaces: number) => text.replace(/\r?\n/g, `\n${" ".repeat(spaces)}`);
const list = (items: string[]) => items.length ? items.map((item) => `- ${indentLines(item, 2)}`).join("\n") : "None recorded.";

export const draftToMarkdown = (draft: FeatureDraft): string => {
  const { spec } = draft;
  return [
    `# ${spec.title}`,
    `Draft ${draft.id} · ${draft.revision ? `Based on saved revision ${draft.revision}` : "Not saved yet"}\nSource: ${draft.source === "example" ? "Example (not AI generated)" : draft.source === "ai" ? `AI draft (${draft.model}) — human review required` : "Manual draft"}`,
    `Last edited or saved: ${draft.updatedAt}${draft.generatedAt ? `\nGenerated: ${draft.generatedAt}` : ""}`,
    "## Problem", spec.problem, "## Target user", spec.targetUser, "## Success metric", spec.successMetric,
    "## In scope", list(spec.inScope), "## Out of scope", list(spec.outOfScope),
    "## User stories", spec.userStories.map((story) => `### ${story.id}\nAs ${story.persona}, I want to ${story.goal}, so that ${story.benefit}.`).join("\n\n"),
    "## Acceptance criteria", "Checks record personal review for clarity, not executed tests or team approval.",
    spec.acceptanceCriteria.map((criterion) => `- [${draft.checkedIds.includes(criterion.id) ? "x" : " "}] ${criterion.id}\n  - Given ${indentLines(criterion.given, 4)}\n  - When ${indentLines(criterion.when, 4)}\n  - Then ${indentLines(criterion.then, 4)}`).join("\n"),
    "## Assumptions to validate", list(spec.assumptions), "## Open questions", list(spec.openQuestions),
    "## Risks and constraints", list(spec.risks),
    "## Original brief", draft.note.split("\n").map((line) => `> ${line}`).join("\n"),
    "## Engineering handoff", "Resolve open questions and validate assumptions before implementation. Confirm scope and acceptance criteria with the team. This draft does not assert feasibility, implementation completion, or passing tests.",
  ].join("\n\n");
};
