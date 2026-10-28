"use client";

import { useId } from "react";
import type { FeatureSpec } from "../lib/feature-spec";
import { ReviewButton, ReviewField, ReviewSection } from "./FeatureReviewFields";

type Criterion = FeatureSpec["acceptanceCriteria"][number];

export const FeatureReviewCriteria = ({ criteria, onChange }: {
  criteria: Criterion[];
  onChange: (criteria: Criterion[]) => void;
}) => {
  const updateCriterion = (id: string, field: "given" | "when" | "then", value: string) => {
    onChange(criteria.map((criterion) => criterion.id === id ? { ...criterion, [field]: value } : criterion));
  };

  return (
    <ReviewSection
      title="Acceptance criteria"
      description="Make the expected behavior specific enough for an engineer to implement and test."
      action={<ReviewButton onClick={() => onChange([...criteria, { id: crypto.randomUUID(), given: "", when: "", then: "" }])}>+ Add criterion</ReviewButton>}
    >
      <div className="space-y-4">
        {criteria.length === 0 && <p className="rounded-xl border border-dashed border-outline-variant p-5 text-sm text-on-surface-variant">No acceptance criteria yet. Add a scenario with an observable expected result.</p>}
        {criteria.map((criterion, index) => (
          <fieldset key={criterion.id} className="min-w-0 rounded-xl border border-outline-variant bg-surface-container-low p-4 sm:p-5">
            <legend className="px-2 text-xs font-medium uppercase tracking-wider text-primary">Criterion {index + 1}</legend>
            <div className="grid gap-4 md:grid-cols-3">
              <ReviewField label="Given" value={criterion.given} onChange={(value) => updateCriterion(criterion.id, "given", value)} multiline rows={3} />
              <ReviewField label="When" value={criterion.when} onChange={(value) => updateCriterion(criterion.id, "when", value)} multiline rows={3} />
              <ReviewField label="Then" value={criterion.then} onChange={(value) => updateCriterion(criterion.id, "then", value)} multiline rows={3} />
            </div>
            <div className="mt-4 flex justify-end">
              <ReviewButton label={`Remove criterion ${index + 1}`} onClick={() => onChange(criteria.filter((item) => item.id !== criterion.id))}>Remove criterion</ReviewButton>
            </div>
          </fieldset>
        ))}
      </div>
    </ReviewSection>
  );
};

export const FeatureReadiness = ({ criteria, checkedIds, onCheckedChange }: {
  criteria: Criterion[];
  checkedIds: string[];
  onCheckedChange: (ids: string[]) => void;
}) => {
  const id = useId();
  const validIds = criteria.map((criterion) => criterion.id);
  const reviewed = checkedIds.filter((checkedId) => validIds.includes(checkedId));
  const toggleCriterion = (criterionId: string, checked: boolean) => {
    onCheckedChange(checked ? [...new Set([...reviewed, criterionId])] : reviewed.filter((item) => item !== criterionId));
  };

  return (
    <ReviewSection title="Review readiness" description="Check each criterion after you have reviewed its clarity and agreed on the expected behavior.">
      <div className="mb-5 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl bg-primary/5 px-4 py-3">
        <p className="text-sm font-medium text-primary" role="status">{reviewed.length} of {criteria.length} criteria reviewed</p>
        <p id={`${id}-help`} className="text-xs leading-5 text-on-surface-variant">This records human review, not passing tests. Editing the spec resets these checks.</p>
      </div>
      {criteria.length === 0 && <p className="text-sm text-on-surface-variant">Add acceptance criteria before reviewing readiness.</p>}
      <div className="space-y-3">
        {criteria.map((criterion, index) => {
          const complete = Boolean(criterion.given.trim() && criterion.when.trim() && criterion.then.trim());
          const inputId = `${id}-${criterion.id}`;
          return (
            <div key={criterion.id} className="flex items-start gap-3 rounded-xl border border-outline-variant p-4">
              <input
                id={inputId}
                type="checkbox"
                checked={reviewed.includes(criterion.id)}
                disabled={!complete}
                onChange={(event) => toggleCriterion(criterion.id, event.target.checked)}
                aria-describedby={`${id}-help ${inputId}-detail`}
                className="mt-1 h-5 w-5 shrink-0 cursor-pointer accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-40"
              />
              <div className="min-w-0">
                <label htmlFor={inputId} className="cursor-pointer text-sm font-medium text-on-surface">Criterion {index + 1} reviewed for clarity</label>
                <p id={`${inputId}-detail`} className="mt-1 break-words text-sm leading-6 text-on-surface-variant">
                  {complete ? <>Given {criterion.given}, when {criterion.when}, then {criterion.then}.</> : "Complete Given, When, and Then before marking this criterion reviewed."}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </ReviewSection>
  );
};
