import { z } from "zod";

const statement = z.string().trim().min(1).max(2000);
const identifier = z.string().trim().regex(/^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$/);
const statements = z.array(statement).max(30);

export const featureSpecSchema = z.strictObject({
  title: z.string().trim().min(1).max(160),
  problem: statement,
  targetUser: statement,
  successMetric: statement,
  inScope: statements.min(1),
  outOfScope: statements,
  userStories: z.array(z.strictObject({
    id: identifier,
    persona: statement,
    goal: statement,
    benefit: statement,
  })).min(1).max(30),
  acceptanceCriteria: z.array(z.strictObject({
    id: identifier,
    given: statement,
    when: statement,
    then: statement,
  })).min(1).max(30),
  assumptions: statements,
  openQuestions: statements,
  risks: statements,
}).superRefine((spec, context) => {
  for (const field of ["userStories", "acceptanceCriteria"] as const) {
    const seen = new Set<string>();
    spec[field].forEach((entry, index) => {
      if (seen.has(entry.id)) {
        context.addIssue({ code: "custom", message: "Identifiers must be unique.", path: [field, index, "id"] });
      }
      seen.add(entry.id);
    });
  }
});

export type FeatureSpec = z.infer<typeof featureSpecSchema>;

export const generateRequestSchema = z.strictObject({
  note: z.string().trim().min(30, "Describe the feature in at least 30 characters.")
    .max(12000, "Keep the feature brief within 12,000 characters."),
});
