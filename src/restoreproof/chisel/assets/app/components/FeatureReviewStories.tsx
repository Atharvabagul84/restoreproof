"use client";

import type { FeatureSpec } from "../lib/feature-spec";
import { ReviewButton, ReviewField, ReviewSection } from "./FeatureReviewFields";

type UserStory = FeatureSpec["userStories"][number];

export const FeatureReviewStories = ({ stories, onChange }: {
  stories: UserStory[];
  onChange: (stories: UserStory[]) => void;
}) => {
  const updateStory = (id: string, field: "persona" | "goal" | "benefit", value: string) => {
    onChange(stories.map((story) => story.id === id ? { ...story, [field]: value } : story));
  };

  return (
    <ReviewSection
      title="User stories"
      description="Describe who needs the feature, what they need to do, and why it matters."
      action={<ReviewButton onClick={() => onChange([...stories, { id: crypto.randomUUID(), persona: "", goal: "", benefit: "" }])}>+ Add story</ReviewButton>}
    >
      <div className="space-y-4">
        {stories.length === 0 && <p className="rounded-xl border border-dashed border-outline-variant p-5 text-sm text-on-surface-variant">No user stories yet. Add a story to describe the intended user outcome.</p>}
        {stories.map((story, index) => (
          <fieldset key={story.id} className="min-w-0 rounded-xl border border-outline-variant bg-surface-container-low p-4 sm:p-5">
            <legend className="px-2 text-xs font-medium uppercase tracking-wider text-primary">Story {index + 1}</legend>
            <div className="grid gap-4 md:grid-cols-3">
              <ReviewField label="As a" value={story.persona} onChange={(value) => updateStory(story.id, "persona", value)} multiline rows={3} />
              <ReviewField label="I want to" value={story.goal} onChange={(value) => updateStory(story.id, "goal", value)} multiline rows={3} />
              <ReviewField label="So that" value={story.benefit} onChange={(value) => updateStory(story.id, "benefit", value)} multiline rows={3} />
            </div>
            <div className="mt-4 flex justify-end">
              <ReviewButton label={`Remove story ${index + 1}`} onClick={() => onChange(stories.filter((item) => item.id !== story.id))}>Remove story</ReviewButton>
            </div>
          </fieldset>
        ))}
      </div>
    </ReviewSection>
  );
};
