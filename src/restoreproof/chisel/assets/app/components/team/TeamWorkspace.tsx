"use client";

import { useState } from "react";
import Link from "next/link";
import { useTeamWorkspace } from "./useTeamWorkspace";
import TeamBriefEditor from "./TeamBriefEditor";
import TeamMembers from "./TeamMembers";
import LocalDraftImport from "./LocalDraftImport";
import { teamInput, teamPrimary, teamSecondary } from "./team-client";

export default function TeamWorkspace({ email, initialWorkspace }: { email: string; initialWorkspace?: string }) {
  const state = useTeamWorkspace(initialWorkspace);
  const [name, setName] = useState("");
  const { detail, editor, busy } = state;
  return <div className="min-h-screen bg-background text-on-surface">
    <a href="#team-workspace" className="sr-only focus:not-sr-only focus:block focus:p-3">Skip to team workspace</a>
    <header className="border-b border-outline-variant bg-surface-container-low"><div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-8">
      <div className="flex items-center gap-3"><span aria-hidden className="flex size-9 items-center justify-center rounded-xl bg-primary text-xl font-bold text-on-primary">⌁</span><span className="text-xl font-semibold tracking-tight">Chisel</span><span className="rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-xs text-primary">Team workspace</span></div>
      <div className="flex flex-wrap items-center gap-4"><span className="max-w-60 truncate text-xs text-on-surface-variant" title={email}>{email}</span><Link href="/" onClick={(event) => { if (!state.canLeave()) event.preventDefault(); }} className="text-xs underline underline-offset-4">Local drafts</Link><button type="button" disabled={busy} className={teamSecondary} onClick={state.signout}>Sign out</button></div>
    </div></header>
    <div className="mx-auto grid max-w-[1440px] gap-8 px-5 py-8 sm:px-8 lg:grid-cols-[250px_minmax(0,1fr)] lg:gap-12">
      <aside aria-label="Team workspace navigation" className="min-w-0 space-y-6">
        <div><label htmlFor="workspace-select" className="text-xs font-semibold uppercase tracking-[0.14em] text-primary">Your workspaces</label><select id="workspace-select" disabled={busy || !state.workspaces.length} value={detail?.workspace.id ?? ""} onChange={(event) => state.selectWorkspace(event.target.value)} className={`${teamInput} mt-3`}><option value="" disabled>{busy ? "Loading…" : "Choose a workspace"}</option>{state.workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}</select><button type="button" disabled={busy} onClick={() => void state.refresh()} className="mt-3 text-xs text-on-surface-variant underline underline-offset-4 disabled:opacity-40">Refresh workspace list</button></div>
        <details open={!busy && state.workspaces.length === 0} className="rounded-xl border border-outline-variant p-4"><summary className="cursor-pointer text-sm font-medium">Create a workspace</summary><form onSubmit={(event) => { event.preventDefault(); void state.createWorkspace(name.trim()); }} className="mt-4"><label htmlFor="workspace-name" className="text-xs">Workspace name</label><input id="workspace-name" required maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="Product & Engineering" className={`${teamInput} mt-2`} disabled={busy} /><button disabled={busy || !name.trim()} className={`${teamPrimary} mt-3 w-full`}>Create workspace</button></form></details>
        {detail && <div><div className="flex items-center justify-between gap-2"><h2 className="text-sm font-semibold">Shared briefs <span className="text-on-surface-variant">{detail.briefs.length}</span></h2><button type="button" onClick={state.newDraft} disabled={busy} className="text-xs text-primary underline underline-offset-4 disabled:opacity-40">+ New brief</button></div><ul className="mt-4 space-y-3">{detail.briefs.map((brief) => <li key={brief.id}><button type="button" disabled={busy} onClick={() => state.openDraft(brief.draft)} className={`w-full rounded-xl border p-4 text-left text-sm disabled:opacity-50 ${editor.draft?.id === brief.id ? "border-primary/50 bg-primary/5" : "border-outline-variant bg-surface-container hover:border-outline"}`}>{brief.draft.spec.title || "Untitled feature"}<span className="mt-2 block text-xs text-on-surface-variant">Saved revision {brief.revision}</span></button></li>)}</ul>{detail.briefs.length === 0 && <p className="mt-4 rounded-xl border border-dashed border-outline p-4 text-xs leading-6 text-on-surface-variant">Saved team briefs will appear here.</p>}<LocalDraftImport busy={busy} onImport={(draft) => state.openDraft(draft, true)} /></div>}
      </aside>
      <main id="team-workspace" className="min-w-0 pb-16">
        {state.error && <div role="alert" className="mb-6 rounded-xl border border-red-400/30 bg-red-400/5 p-4 text-sm leading-6 text-red-200">{state.error}<p className="mt-2 text-xs">Your current edits are kept here. Download a backup before signing in again or leaving.</p></div>}
        {state.notice && <p role="status" className="mb-6 rounded-xl border border-tertiary/25 bg-tertiary/5 p-4 text-sm leading-6 text-tertiary-fixed">{state.notice}</p>}
        {busy && <p role="status" className="mb-5 text-sm text-primary">Updating workspace…</p>}
        {detail ? <>
          <div className="mb-6"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{detail.workspace.name}</p><p className="mt-2 text-xs capitalize text-on-surface-variant">Your role: {detail.workspace.role === "pm" ? "Product manager" : detail.workspace.role}</p></div>
          <TeamMembers key={detail.workspace.id} members={detail.members} invitations={detail.invitations} owner={detail.workspace.role === "owner"} busy={busy} invitePath={state.invitePath} onInvite={(email, role) => void state.invite(email, role)} onRemove={state.removeMember} onRevoke={(id) => void state.revokeInvitation(id)} />
          {editor.draft ? <TeamBriefEditor key={editor.draft.id} draft={editor.draft} dirty={editor.dirty} conflict={editor.conflict} busy={busy} workspaceId={detail.workspace.id} onChange={state.updateDraft} onSave={() => void state.save()} onReload={state.reloadDraft} /> : <div className="rounded-2xl border border-outline-variant bg-surface-container p-6 sm:p-10"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">A shared understanding</p><h1 className="mt-4 max-w-xl text-4xl font-semibold leading-tight tracking-tight">One brief.<br />The whole team’s context.</h1><p className="mt-5 max-w-xl text-sm leading-7 text-on-surface-variant">Write the problem, define the scope, and make open questions visible. Invite your PM and engineers to edit the same saved brief.</p><button type="button" disabled={busy} onClick={state.newDraft} className={`${teamPrimary} mt-6`}>Write the first draft</button><p className="mt-4 text-xs leading-6 text-on-surface-variant">You can also bring an existing browser draft from the sidebar.</p></div>}
        </> : !busy && <div className="rounded-2xl border border-outline-variant p-6 sm:p-10"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Start together</p><h1 className="mt-4 text-4xl font-semibold tracking-tight">Create your team’s workspace.</h1><p className="mt-5 max-w-xl text-sm leading-7 text-on-surface-variant">Your account is ready. Give your workspace a name to start sharing feature briefs. If a teammate invited you, open their invitation link while signed in with the invited email.</p></div>}
      </main>
    </div>
  </div>;
}
