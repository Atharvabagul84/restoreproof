"use client";

import { useState } from "react";
import FeatureReview from "../FeatureReview";
import { featureSpecSchema } from "../../lib/feature-spec";
import { draftSchema, draftToMarkdown, type FeatureDraft } from "../../lib/local-drafts";
import { teamError, teamInput, teamPrimary, teamSecondary } from "./team-client";

type Props = { draft: FeatureDraft; dirty: boolean; conflict: boolean; busy: boolean; workspaceId: string; onChange: (draft: FeatureDraft) => void; onSave: () => void; onReload: () => void };

export default function TeamBriefEditor({ draft, dirty, conflict, busy, workspaceId, onChange, onSave, onReload }: Props) {
  const [exportError, setExportError] = useState("");
  const exportDraft = (format: "json" | "markdown") => {
    setExportError("");
    try {
      const snapshot = draftSchema.parse(draft);
      const complete = featureSpecSchema.safeParse(snapshot.spec);
      if (format === "markdown" && !complete.success) throw new Error(`Complete ${complete.error.issues[0].path.join(" → ")} before a Markdown handoff. JSON backup supports unfinished drafts.`);
      const exportedAt = new Date().toISOString();
      const content = format === "json"
        ? JSON.stringify({ schemaVersion: 1, ...snapshot, workspaceId, exportedAt, hasUnsavedChanges: dirty, complete: complete.success }, null, 2)
        : `${draftToMarkdown(snapshot)}\n\nWorkspace: ${workspaceId}\nExported: ${exportedAt}\n${dirty ? "Working copy includes unsaved edits." : "Matches the saved content."}\nReview checks are personal to this browser session and are not shared approval.`;
      const url = URL.createObjectURL(new Blob([content], { type: format === "json" ? "application/json" : "text/markdown;charset=utf-8" }));
      const anchor = document.createElement("a"); anchor.href = url;
      anchor.download = `${draft.spec.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 70) || "feature"}.${format === "json" ? "json" : "md"}`;
      anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setExportError(teamError(failure)); }
  };
  return <section aria-label="Shared feature editor">
    <div className="mb-6"><p className="text-xs font-medium text-primary">{draft.source === "example" ? "Example content" : draft.source === "ai" ? "AI draft · needs review" : "Manual draft"} · {draft.revision ? `Revision ${draft.revision}` : "New draft"} · {dirty ? "Unsaved changes" : "Saved"}</p><h2 className="mt-3 text-3xl font-semibold tracking-tight">Shape the shared brief.</h2><p className="mt-3 text-sm leading-6 text-on-surface-variant">Everyone in this workspace can edit. Saves create a new revision; a newer team edit will never be overwritten silently.</p></div>
    {conflict && <div role="alert" className="mb-5 rounded-xl border border-amber-300/30 bg-amber-300/5 p-4 text-sm leading-6 text-amber-200">A teammate saved a newer revision. Your edits are still here. Download a JSON backup, then load the latest version and combine your changes.<button type="button" onClick={onReload} disabled={busy} className="mt-3 block underline underline-offset-4">Load latest revision</button></div>}
    {exportError && <p role="alert" className="mb-5 rounded-xl border border-red-400/30 p-4 text-sm text-red-200">{exportError}</p>}
    <div className="sticky top-0 z-10 mb-6 flex flex-wrap gap-2 rounded-xl border border-outline-variant bg-background/95 p-3 backdrop-blur">
      <button type="button" disabled={busy || !dirty || conflict} onClick={onSave} className={teamPrimary}>{busy ? "Working…" : "Save in workspace"}</button>
      <button type="button" onClick={() => exportDraft("json")} className={teamSecondary}>Download JSON backup</button>
      <button type="button" onClick={() => exportDraft("markdown")} className={teamSecondary}>Download Markdown</button>
      {!!draft.revision && !conflict && <button type="button" disabled={busy} onClick={onReload} className={teamSecondary}>Load latest</button>}
    </div>
    <fieldset disabled={busy} className="min-w-0 border-0 p-0 disabled:opacity-60">
      <details className="mb-6 rounded-xl border border-outline-variant p-4"><summary className="cursor-pointer text-sm font-medium">Original notes & context</summary><label htmlFor="team-source-note" className="mt-4 block text-xs text-on-surface-variant">Keep the customer context alongside your specification.</label><textarea id="team-source-note" value={draft.note} maxLength={12000} rows={5} onChange={(event) => onChange({ ...draft, note: event.target.value, checkedIds: [] })} className={`${teamInput} mt-3 resize-y leading-7`} /></details>
      <p className="mb-5 text-xs leading-6 text-on-surface-variant">Checklist marks are personal review aids for this session. Saving clears them; they do not record a teammate’s approval or completed tests.</p>
      <FeatureReview spec={draft.spec} checkedIds={draft.checkedIds} onChange={(spec) => onChange({ ...draft, spec, checkedIds: [] })} onCheckedChange={(checkedIds) => onChange({ ...draft, checkedIds })} />
    </fieldset>
  </section>;
}
