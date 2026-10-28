"use client";

import { useState } from "react";
import { DRAFT_STORAGE_KEY, parseDrafts, type FeatureDraft } from "../../lib/local-drafts";
import { copyToTeam } from "./editor-state";
import { teamSecondary } from "./team-client";

export default function LocalDraftImport({ busy, onImport }: { busy: boolean; onImport: (draft: FeatureDraft) => void }) {
  const [drafts, setDrafts] = useState<FeatureDraft[] | null>(null);
  const [error, setError] = useState("");
  const inspect = () => {
    try { setDrafts(parseDrafts(localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]")); setError(""); }
    catch { setError("Browser drafts could not be read. Existing local data has been preserved."); }
  };
  return <div className="mt-5 border-t border-outline-variant pt-5">
    <button type="button" disabled={busy} onClick={inspect} className={teamSecondary}>Bring a browser draft</button>
    {error && <p role="alert" className="mt-3 text-xs leading-5 text-red-200">{error}</p>}
    {drafts && <div className="mt-3"><p className="text-xs leading-6 text-on-surface-variant">Choose a local draft to copy. It will be shared only after you click Save in workspace.</p>{drafts.length === 0 && <p className="mt-2 text-xs text-on-surface-variant">No drafts saved in this browser.</p>}<ul className="mt-3 space-y-2">{drafts.map((draft) => <li key={draft.id}><button type="button" disabled={busy} onClick={() => onImport(copyToTeam(draft, crypto.randomUUID(), new Date().toISOString()))} className="w-full rounded-lg border border-outline-variant p-3 text-left text-xs hover:border-primary disabled:opacity-40">{draft.spec.title || "Untitled feature"}<span className="mt-1 block text-on-surface-variant">Copy local revision {draft.revision}</span></button></li>)}</ul></div>}
  </div>;
}
