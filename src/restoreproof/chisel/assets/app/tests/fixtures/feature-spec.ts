export const sampleFeatureSpec = {
  title: "Team ownership",
  problem: "Engineers do not know who owns incoming work.",
  targetUser: "An engineering manager",
  successMetric: "To be agreed",
  inScope: ["Assign an owner to an incoming task."],
  outOfScope: ["Automatic workload prediction."],
  userStories: [{ id: "US-1", persona: "an engineering manager", goal: "assign a task owner", benefit: "responsibility is clear" }],
  acceptanceCriteria: [{ id: "AC-1", given: "an unassigned task", when: "a manager assigns an owner", then: "the task displays that owner" }],
  assumptions: ["A manager may assign tasks."],
  openQuestions: ["Which roles can change an owner?"],
  risks: ["Permission rules require agreement."],
};
