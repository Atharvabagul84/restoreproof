"use client";

import { useEffect, useRef, useState } from "react";
import { featureSpecSchema, type FeatureSpec } from "../lib/feature-spec";
import { DRAFT_STORAGE_KEY, DraftSaveError, draftSchema, draftToMarkdown, parseDrafts, saveDraft, type FeatureDraft } from "../lib/local-drafts";
import { EXAMPLE_NOTE, EXAMPLE_SPEC, manualFeature } from "../lib/example-feature";

const errorText = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";

export const useFeatureWorkspace = () => {
  const [note, setNote] = useState("");
  const [draft, setDraft] = useState<FeatureDraft | null>(null);
  const [drafts, setDrafts] = useState<FeatureDraft[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [remaining, setRemaining] = useState<number | null>(null);
  const request = useRef<AbortController | null>(null);

  useEffect(() => {
    // Synchronize browser-owned storage after hydration; never read it during SSR.
    try {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setDrafts(parseDrafts(localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]"));
    } catch {
      setError("Saved drafts could not be read. Existing browser data has been preserved. Export your current work before clearing site data.");
    }
    return () => request.current?.abort();
  }, []);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (dirty || (!draft && note.trim())) event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, draft, note]);

  const clearMessages = () => { setError(""); setNotice(""); };
  const cancel = () => { request.current?.abort(); request.current = null; setBusy(false); setNotice("Generation cancelled. Your brief is still here."); };
  const canLeave = () => !(dirty || (!draft && note.trim())) || window.confirm("Leave this unsaved work? Save or export a draft first to keep it.");
  const newBrief = () => {
    if (!canLeave()) return;
    cancel(); setDraft(null); setNote(""); setDirty(false); clearMessages();
  };
  const startDraft = (spec: FeatureSpec, source: FeatureDraft["source"], brief: string, model: string | null = null, generatedAt: string | null = null) => {
    setDraft({ id: crypto.randomUUID(), spec: structuredClone(spec), note: brief, source, model, generatedAt, updatedAt: new Date().toISOString(), revision: 0, checkedIds: [] });
    setNote(brief); setDirty(true);
  };
  const example = () => { if (!canLeave()) return; cancel(); clearMessages(); startDraft(EXAMPLE_SPEC, "example", EXAMPLE_NOTE); };
  const manual = () => { clearMessages(); startDraft(manualFeature(), "manual", note); };
  const reopen = (saved: FeatureDraft) => {
    if (!canLeave()) return;
    cancel(); clearMessages(); setDraft(structuredClone(saved)); setNote(saved.note); setDirty(false);
  };

  const generate = async () => {
    if (busy) return;
    clearMessages();
    const brief = note.trim();
    if (brief.length < 30 || brief.length > 12000) { setError("Add a brief between 30 and 12,000 characters."); return; }
    const controller = new AbortController();
    request.current = controller; setBusy(true);
    try {
      const response = await fetch("/api/generate-prd", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note: brief }), signal: controller.signal });
      const result = await response.json();
      if (request.current !== controller || controller.signal.aborted) return;
      const left = Number(response.headers.get("RateLimit-Remaining") ?? NaN);
      if (Number.isInteger(left) && left >= 0) setRemaining(left);
      else if (response.status === 429 && result.code === "rate_limited") setRemaining(0);
      if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : "Generation failed. Please try again.");
      const spec = featureSpecSchema.parse(result.spec);
      if (typeof result.model !== "string" || typeof result.generatedAt !== "string" || !Number.isFinite(Date.parse(result.generatedAt))) throw new Error("The generation response was incomplete. Please try again.");
      startDraft(spec, "ai", brief, result.model, result.generatedAt);
      setNotice("AI draft created. Review the content and open questions before handing it to engineering.");
    } catch (failure) {
      if (!controller.signal.aborted) setError(errorText(failure));
    } finally {
      if (request.current === controller) { request.current = null; setBusy(false); }
    }
  };

  const updateSpec = (spec: FeatureSpec) => { setDraft((current) => current ? { ...current, spec, checkedIds: [], updatedAt: new Date().toISOString() } : null); setDirty(true); setNotice(""); };
  const updateChecks = (checkedIds: string[]) => { setDraft((current) => current ? { ...current, checkedIds, updatedAt: new Date().toISOString() } : null); setDirty(true); setNotice(""); };
  const save = (): FeatureDraft | null => {
    if (!draft) return null;
    clearMessages();
    const valid = draftSchema.safeParse(draft);
    if (!valid.success) { const issue = valid.error.issues[0]; setError(`Check ${issue.path.join(" → ")}: ${issue.message}`); return null; }
    try {
      const latest = parseDrafts(localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]");
      const next = saveDraft(latest, valid.data);
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(next));
      setDrafts(next); setDraft(next[0]); setDirty(false); setNotice("Saved in this browser. Download a copy for backup or handoff.");
      return next[0];
    } catch (failure) {
      setError(failure instanceof DraftSaveError ? failure.message : "Could not save to browser storage. It may be full, blocked, or contain unreadable data. Use Download to keep a copy of your work.");
      return null;
    }
  };
  const exportDraft = async (format: "markdown" | "json" | "copy") => {
    if (!draft) return;
    clearMessages();
    const valid = draftSchema.safeParse(draft);
    if (!valid.success) { setError(`Check this field before exporting: ${valid.error.issues[0].path.join(" → ")}.`); return; }
    const complete = featureSpecSchema.safeParse(valid.data.spec);
    if (format !== "json" && !complete.success) { setError(`Complete ${complete.error.issues[0].path.join(" → ")} before a Markdown handoff. You can save this unfinished draft or export JSON now.`); return; }
    // Export is independent of storage, so a full browser quota cannot trap the user's work.
    const snapshot = valid.data;
    const exportedAt = new Date().toISOString();
    const markdown = `${draftToMarkdown(snapshot)}\n\nExported: ${exportedAt}\n${dirty ? "Working copy includes unsaved edits." : "Matches the saved draft."}`;
    try {
      if (format === "copy") await navigator.clipboard.writeText(markdown);
      else {
        const content = format === "json" ? JSON.stringify({ schemaVersion: 1, ...snapshot, exportedAt, hasUnsavedChanges: dirty, complete: complete.success }, null, 2) : markdown;
        const url = URL.createObjectURL(new Blob([content], { type: format === "json" ? "application/json" : "text/markdown;charset=utf-8" }));
        const anchor = document.createElement("a"); anchor.href = url;
        anchor.download = `${draft.spec.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 70) || "feature"}.${format === "json" ? "json" : "md"}`;
        anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
      setNotice(format === "copy" ? "Markdown copied, including your current edits." : "Export created, including your current edits.");
    } catch { setError("Export failed. Try downloading instead of copying, or check browser permissions."); }
  };
  const remove = (id: string) => {
    if (!window.confirm("Remove this saved draft from this browser? Download it first if you need a backup.")) return;
    try {
      const next = parseDrafts(localStorage.getItem(DRAFT_STORAGE_KEY) ?? "[]").filter((item) => item.id !== id);
      localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(next)); setDrafts(next);
      if (draft?.id === id) setDirty(true);
      setNotice("Saved draft removed.");
    } catch { setError("Could not remove the draft. Browser data has been preserved."); }
  };
  return { note, setNote, draft, drafts, dirty, busy, error, notice, remaining, newBrief, example, manual, reopen, generate, cancel, updateSpec, updateChecks, save, exportDraft, remove };
};
