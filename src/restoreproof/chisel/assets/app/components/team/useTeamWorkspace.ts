"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import type { TeamBrief, TeamInvitation, TeamMember, WorkspaceSummary } from "../../lib/team/contracts";
import { manualFeature } from "../../lib/example-feature";
import type { FeatureDraft } from "../../lib/local-drafts";
import { emptyEditor, teamEditorReducer } from "./editor-state";
import { teamError, teamRequest, TeamRequestError } from "./team-client";

export type WorkspaceDetail = { workspace: WorkspaceSummary; members: TeamMember[]; invitations: TeamInvitation[]; briefs: TeamBrief[] };

export const useTeamWorkspace = (initialWorkspace?: string) => {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [detail, setDetail] = useState<WorkspaceDetail | null>(null);
  const [editor, dispatch] = useReducer(teamEditorReducer, emptyEditor);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [invitePath, setInvitePath] = useState("");
  const pending = useRef(false);
  const leaving = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const result = await teamRequest<{ workspaces: WorkspaceSummary[] }>("/api/team/workspaces", { signal: controller.signal });
        if (controller.signal.aborted) return;
        setWorkspaces(result.workspaces);
        const selected = result.workspaces.find((item) => item.id === initialWorkspace) ?? result.workspaces[0];
        if (selected) {
          const next = await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${selected.id}`, { signal: controller.signal });
          if (!controller.signal.aborted) setDetail(next);
        }
      } catch (failure) { if (!controller.signal.aborted) setError(teamError(failure)); }
      finally { if (!controller.signal.aborted) setBusy(false); }
    };
    void load();
    return () => controller.abort();
  }, [initialWorkspace]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (editor.dirty && !leaving.current) event.preventDefault(); };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [editor.dirty]);

  const canLeave = () => !busy && !pending.current && (!editor.dirty || window.confirm("Leave these unsaved edits? Save in your workspace or download a JSON backup first."));
  const run = async (action: () => Promise<void>) => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError(""); setNotice("");
    try { await action(); }
    catch (failure) { setError(teamError(failure)); }
    finally { pending.current = false; setBusy(false); }
  };
  const refresh = () => run(async () => {
    const result = await teamRequest<{ workspaces: WorkspaceSummary[] }>("/api/team/workspaces");
    setWorkspaces(result.workspaces);
    const selected = detail ? result.workspaces.find((item) => item.id === detail.workspace.id) : result.workspaces[0];
    if (detail && !selected) throw new Error("You no longer have access to this workspace. Export any unsaved edits, then choose another workspace.");
    if (selected) setDetail(await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${selected.id}`));
    setNotice("Workspace list refreshed. Your open draft is unchanged; reopen it to load the latest revision.");
  });
  const selectWorkspace = (id: string) => {
    if (!canLeave()) return;
    void run(async () => {
      const next = await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${id}`);
      setDetail(next); dispatch({ type: "clear" }); setInvitePath("");
    });
  };
  const createWorkspace = (name: string) => {
    if (!canLeave()) return;
    return run(async () => {
      const result = await teamRequest<{ id: string }>("/api/team/workspaces", { method: "POST", body: JSON.stringify({ name }) });
      const next = await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${result.id}`);
      setWorkspaces((items) => [...items, next.workspace]); setDetail(next); dispatch({ type: "clear" }); setInvitePath("");
      setNotice("Workspace created. Add a brief or invite your first teammate.");
    });
  };
  const openDraft = (draft: FeatureDraft, isNew = false) => {
    if (!canLeave()) return;
    dispatch({ type: "open", draft });
    if (isNew) dispatch({ type: "change", draft });
    setError(""); setNotice("");
  };
  const newDraft = () => openDraft({ id: crypto.randomUUID(), spec: manualFeature(), note: "", source: "manual", model: null, generatedAt: null, revision: 0, updatedAt: new Date().toISOString(), checkedIds: [] }, true);
  const updateDraft = (draft: FeatureDraft) => {
    if (busy || pending.current) return;
    dispatch({ type: "change", draft: { ...draft, updatedAt: new Date().toISOString() } }); setNotice("");
  };
  const save = () => run(async () => {
    if (!detail || !editor.draft) return;
    try {
      const result = await teamRequest<{ brief: TeamBrief }>(`/api/team/workspaces/${detail.workspace.id}/briefs`, { method: "POST", body: JSON.stringify({ draft: editor.draft, expectedRevision: editor.draft.revision }) });
      dispatch({ type: "saved", draft: result.brief.draft });
      setDetail({ ...detail, briefs: [result.brief, ...detail.briefs.filter((item) => item.id !== result.brief.id)] });
      setNotice(`Saved shared revision ${result.brief.revision}. Personal review checks were cleared; they are not team approval.`);
    } catch (failure) {
      if (failure instanceof TeamRequestError && failure.status === 409) dispatch({ type: "conflict" });
      throw failure;
    }
  });
  const reloadDraft = () => {
    if (!detail || !editor.draft || !canLeave()) return;
    void run(async () => {
      const next = await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${detail.workspace.id}`);
      const latest = next.briefs.find((item) => item.id === editor.draft?.id);
      if (!latest) throw new Error("This draft is no longer available. Your current edits are still here for export.");
      setDetail(next); dispatch({ type: "open", draft: latest.draft }); setNotice("Loaded the latest saved revision.");
    });
  };
  const invite = (email: string, role: "pm" | "engineer") => run(async () => {
    if (!detail) return;
    const result = await teamRequest<{ invitePath: string }>(`/api/team/workspaces/${detail.workspace.id}/invitations`, { method: "POST", body: JSON.stringify({ email, role }) });
    setInvitePath(result.invitePath);
    setDetail(await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${detail.workspace.id}`));
    setNotice("Invitation created. Copy the link and share it with the invited email address. No email has been sent.");
  });
  const removeMember = (member: TeamMember) => {
    if (!detail || !window.confirm(`Remove ${member.email} from this workspace? They will lose access to shared briefs.`)) return;
    void run(async () => {
      await teamRequest(`/api/team/workspaces/${detail.workspace.id}/members/${member.userId}`, { method: "DELETE" });
      setDetail(await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${detail.workspace.id}`));
      setNotice("Member removed from this workspace.");
    });
  };
  const revokeInvitation = (id: string) => run(async () => {
    if (!detail) return;
    await teamRequest(`/api/team/invitations/${id}`, { method: "DELETE" });
    setInvitePath(""); setDetail(await teamRequest<WorkspaceDetail>(`/api/team/workspaces/${detail.workspace.id}`));
    setNotice("Invitation revoked.");
  });
  const signout = () => {
    if (!canLeave()) return;
    void run(async () => {
      await teamRequest("/api/auth/signout", { method: "POST" }); leaving.current = true;
      // Reset the client router cache after the server clears authentication cookies.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.assign("/login");
    });
  };
  return { workspaces, detail, editor, busy, error, notice, invitePath, canLeave, refresh, selectWorkspace, createWorkspace, openDraft, newDraft, updateDraft, save, reloadDraft, invite, removeMember, revokeInvitation, signout };
};
