import type { FeatureSpec } from "./feature-spec";

export const EXAMPLE_NOTE = "Our support leads copy filtered tickets into spreadsheets every Friday. Add a CSV export to the ticket list using the current status and date filters. Only support leads should export. Include ticket ID, title, status, owner and created date. Empty results should still download a file with headers. Scheduled exports and attachments are out of scope. We have not agreed a maximum export size or a success target.";

export const EXAMPLE_SPEC: FeatureSpec = {
  title: "Export filtered support tickets",
  problem: "Support leads manually copy ticket data into spreadsheets to prepare weekly reports.",
  targetUser: "Support leads preparing weekly reports",
  successMetric: "To be agreed: measure time spent preparing the weekly ticket report.",
  inScope: ["CSV download using the current status and date filters", "Columns: ticket ID, title, status, owner and created date", "Restrict exports to support leads", "Include column headers when no tickets match"],
  outOfScope: ["Scheduled exports", "Ticket attachments"],
  userStories: [
    { id: "US-001", persona: "a support lead", goal: "export the filtered ticket list", benefit: "I can prepare a weekly report without copying each row" },
    { id: "US-002", persona: "a support lead", goal: "download consistent column headers even for empty results", benefit: "my reporting template remains usable" },
  ],
  acceptanceCriteria: [
    { id: "AC-001", given: "a support lead has selected status and date filters", when: "they export the ticket list", then: "the downloaded CSV contains only matching tickets and the five requested columns" },
    { id: "AC-002", given: "no tickets match the selected filters", when: "a support lead exports", then: "the CSV contains headers and no ticket rows" },
    { id: "AC-003", given: "a user is not a support lead", when: "they request a ticket export", then: "the system refuses access and does not expose ticket data" },
  ],
  assumptions: ["The existing application can identify a support lead; confirm the role mapping."],
  openQuestions: ["What is the maximum export size and expected behavior above it?", "Which date field and timezone should filters use?", "What baseline and improvement target should define success?"],
  risks: ["Ticket text can contain spreadsheet formulas; engineering should define safe CSV encoding.", "Exported data may contain customer information; confirm access and retention expectations."],
};

export const manualFeature = (): FeatureSpec => ({
  title: "Untitled feature", problem: "Describe the problem to solve.", targetUser: "Identify the target user.",
  successMetric: "To be agreed", inScope: ["Define the smallest useful scope."], outOfScope: [],
  userStories: [{ id: "US-001", persona: "the target user", goal: "describe their goal", benefit: "describe the value" }],
  acceptanceCriteria: [{ id: "AC-001", given: "describe the starting context", when: "describe the action", then: "describe the observable outcome" }],
  assumptions: [], openQuestions: ["Confirm the problem, scope and acceptance criteria with your team."], risks: [],
});
