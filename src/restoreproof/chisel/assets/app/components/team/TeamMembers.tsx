"use client";

import { useState } from "react";
import type { TeamInvitation, TeamMember } from "../../lib/team/contracts";
import { teamInput, teamPrimary, teamSecondary } from "./team-client";

type Props = { members: TeamMember[]; invitations: TeamInvitation[]; owner: boolean; busy: boolean; invitePath: string; onInvite: (email: string, role: "pm" | "engineer") => void; onRemove: (member: TeamMember) => void; onRevoke: (id: string) => void };
export default function TeamMembers({ members, invitations, owner, busy, invitePath, onInvite, onRemove, onRevoke }: Props) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"pm" | "engineer">("engineer");
  const [copyMessage, setCopyMessage] = useState("");
  const [loadedAt] = useState(() => Date.now());
  const invitationLink = typeof window === "undefined" || !invitePath ? "" : `${window.location.origin}${invitePath}`;
  const copyLink = async () => {
    try { await navigator.clipboard.writeText(invitationLink); setCopyMessage("Invitation link copied."); }
    catch { setCopyMessage("Copy was blocked. Select and copy the link below."); }
  };
  return <details className="mb-8 rounded-2xl border border-outline-variant bg-surface-container p-5">
    <summary className="cursor-pointer text-sm font-semibold">Team members <span className="ml-2 text-on-surface-variant">{members.length}</span></summary>
    <ul className="mt-5 space-y-3">{members.map((member) => <li key={member.userId} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-background p-3"><div className="min-w-0"><p className="break-all text-sm">{member.email}</p><p className="mt-1 text-xs capitalize text-on-surface-variant">{member.role === "pm" ? "Product manager" : member.role}</p></div>{owner && member.role !== "owner" && <button type="button" disabled={busy} onClick={() => onRemove(member)} className="text-xs text-red-200 underline underline-offset-4 disabled:opacity-40">Remove<span className="sr-only"> {member.email}</span></button>}</li>)}</ul>
    {owner ? <>
      <form onSubmit={(event) => { event.preventDefault(); setCopyMessage(""); onInvite(email.trim(), role); }} className="mt-6 border-t border-outline-variant pt-5">
        <h3 className="text-sm font-medium">Invite a teammate</h3><p className="mt-2 text-xs leading-6 text-on-surface-variant">Create a link for one email address. Share it yourself; it expires after 7 days and can be accepted once.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_170px]"><label className="text-xs">Email<input required type="email" maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy} className={`${teamInput} mt-2`} autoComplete="email" placeholder="teammate@company.com" /></label><label className="text-xs">Role<select disabled={busy} value={role} onChange={(event) => setRole(event.target.value as "pm" | "engineer")} className={`${teamInput} mt-2`}><option value="engineer">Engineer</option><option value="pm">Product manager</option></select></label></div>
        <button disabled={busy || !email.trim()} className={`${teamPrimary} mt-4`}>Create invitation link</button>
      </form>
      {invitationLink && <div className="mt-5 rounded-xl border border-primary/30 bg-primary/5 p-4"><label htmlFor="invitation-link" className="block text-xs font-medium">Share this invitation link with the invited teammate</label><input id="invitation-link" type="text" readOnly value={invitationLink} className={`${teamInput} mt-3`} onFocus={(event) => event.target.select()} /><button type="button" onClick={() => void copyLink()} className={`${teamSecondary} mt-3`}>Copy invitation link</button>{copyMessage && <p role="status" className="mt-2 text-xs text-on-surface-variant">{copyMessage}</p>}</div>}
      {invitations.length > 0 && <><h3 className="mt-6 text-sm font-medium">Invitations</h3><ul className="mt-3 space-y-3">{invitations.map((invitation) => {
        const status = invitation.acceptedAt ? "Accepted" : invitation.revokedAt ? "Revoked" : new Date(invitation.expiresAt).getTime() <= loadedAt ? "Expired" : "Pending";
        return <li key={invitation.id} className="flex flex-wrap items-center justify-between gap-3 text-xs"><span className="break-all text-on-surface-variant">{invitation.email} · {status}</span>{status === "Pending" && <button type="button" disabled={busy} onClick={() => onRevoke(invitation.id)} className="underline underline-offset-4 disabled:opacity-40">Revoke<span className="sr-only"> invitation for {invitation.email}</span></button>}</li>;
      })}</ul></>}
    </> : <p className="mt-5 text-xs leading-6 text-on-surface-variant">PMs and engineers can edit shared briefs. Workspace owners manage membership and invitations.</p>}
  </details>;
}
