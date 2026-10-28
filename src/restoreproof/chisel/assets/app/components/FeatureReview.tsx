"use client";

import { useId } from "react";
import type { FeatureSpec } from "../lib/feature-spec";
import { FeatureReadiness, FeatureReviewCriteria } from "./FeatureReviewCriteria";
import { ReviewField, ReviewListField, ReviewSection } from "./FeatureReviewFields";
import { FeatureReviewStories } from "./FeatureReviewStories";

interface FeatureReviewProps {
  spec: FeatureSpec;
  onChange: (spec: FeatureSpec) => void;
  checkedIds: string[];
  onCheckedChange: (ids: string[]) => void;
}

export default function FeatureReview({ spec, onChange, checkedIds, onCheckedChange }: FeatureReviewProps) {
  const questionsHeadingId = useId();
  const updateSpec = (patch: Partial<FeatureSpec>) => {
    if (checkedIds.length > 0) onCheckedChange([]);
    onChange({ ...spec, ...patch });
  };
  const questionCount = spec.openQuestions.filter((question) => question.trim()).length;

  return (
    <div className="space-y-6">
      <ReviewSection title="Feature brief" description="Review the intent before the details. Every field is editable.">
        <div className="space-y-5">
          <ReviewField label="Feature title" value={spec.title} onChange={(title) => updateSpec({ title })} />
          <ReviewField label="Problem to solve" value={spec.problem} onChange={(problem) => updateSpec({ problem })} multiline rows={4} />
          <div className="grid gap-5 md:grid-cols-2">
            <ReviewField label="Target user" value={spec.targetUser} onChange={(targetUser) => updateSpec({ targetUser })} multiline />
            <ReviewField label="Success metric" value={spec.successMetric} onChange={(successMetric) => updateSpec({ successMetric })} multiline hint="Confirm the measure and target with your team. Leave unvalidated targets explicit." />
          </div>
        </div>
      </ReviewSection>

      <ReviewSection title="Scope boundaries" description="Agree on what this feature includes and what belongs outside this iteration.">
        <div className="grid gap-6 md:grid-cols-2">
          <ReviewListField label="In scope" values={spec.inScope} onChange={(inScope) => updateSpec({ inScope })} />
          <ReviewListField label="Out of scope" values={spec.outOfScope} onChange={(outOfScope) => updateSpec({ outOfScope })} />
        </div>
      </ReviewSection>

      <section className="rounded-2xl border border-amber-400/25 bg-amber-400/[0.04] p-5 sm:p-7" aria-labelledby={questionsHeadingId}>
        <div className="mb-5 flex flex-wrap items-center gap-3">
          <h3 id={questionsHeadingId} className="text-lg font-semibold tracking-tight text-amber-200">Open questions</h3>
          <span className="rounded-full border border-amber-400/20 px-2.5 py-1 text-xs font-medium text-amber-200">{questionCount} to resolve</span>
        </div>
        <p className="mb-5 text-sm leading-6 text-on-surface-variant">Keep missing decisions visible. Resolve these with your team before treating the spec as ready to build.</p>
        <ReviewListField label="Questions for the team" values={spec.openQuestions} onChange={(openQuestions) => updateSpec({ openQuestions })} hint="One question per line. Record the answer in the relevant field before removing a resolved question." />
      </section>

      <FeatureReviewStories stories={spec.userStories} onChange={(userStories) => updateSpec({ userStories })} />
      <FeatureReviewCriteria criteria={spec.acceptanceCriteria} onChange={(acceptanceCriteria) => updateSpec({ acceptanceCriteria })} />

      <ReviewSection title="Assumptions and risks" description="Separate what needs validation from the constraints that could affect delivery.">
        <div className="grid gap-6 md:grid-cols-2">
          <ReviewListField label="Assumptions to validate" values={spec.assumptions} onChange={(assumptions) => updateSpec({ assumptions })} />
          <ReviewListField label="Risks and constraints" values={spec.risks} onChange={(risks) => updateSpec({ risks })} />
        </div>
      </ReviewSection>

      <FeatureReadiness criteria={spec.acceptanceCriteria} checkedIds={checkedIds} onCheckedChange={onCheckedChange} />
    </div>
  );
}
