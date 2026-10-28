"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { teamError, teamPrimary, teamRequest, teamSecondary } from "./team-client";

export default function JoinWorkspace({ token, email }: { token: string; email: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const accept = async () => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try {
      const result = await teamRequest<{ workspaceId: string }>("/api/team/invitations/accept", { method: "POST", body: JSON.stringify({ token }) });
      window.location.replace(`/team?workspace=${encodeURIComponent(result.workspaceId)}`);
    } catch (failure) { setError(teamError(failure)); pending.current = false; setBusy(false); }
  };
  const signout = async () => {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError("");
    try { await teamRequest("/api/auth/signout", { method: "POST" }); window.location.replace(`/login?next=${encodeURIComponent(`/join/${token}`)}`); }
    catch (failure) { setError(teamError(failure)); pending.current = false; setBusy(false); }
  };
  return <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-5 py-12 sm:px-8">
    <Link href="/team" className="mb-10 text-xl font-semibold tracking-tight">⌁ Chisel</Link>
    <div className="rounded-2xl border border-outline-variant bg-surface-container p-6 sm:p-9"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">Workspace invitation</p><h1 className="mt-4 text-3xl font-semibold tracking-tight">Build a shared understanding.</h1><p className="mt-5 text-sm leading-7 text-on-surface-variant">Accept this invitation to view and edit your team’s feature briefs. The link is tied to the email address your workspace owner invited.</p><p className="mt-5 break-all rounded-xl bg-background p-4 text-sm">Signed in as <strong>{email}</strong></p>{error && <p role="alert" className="mt-5 rounded-xl border border-red-400/30 p-4 text-sm leading-6 text-red-200">{error}</p>}<div className="mt-6 flex flex-wrap gap-3"><button type="button" disabled={busy} className={teamPrimary} onClick={() => void accept()}>{busy ? "Working…" : "Accept invitation"}</button><button type="button" disabled={busy} className={teamSecondary} onClick={() => void signout()}>Use another email</button></div><p className="mt-4 text-xs leading-6 text-on-surface-variant">Expired or revoked link? Ask the owner for a new invitation. You have not joined until you accept.</p></div>
  </main>;
}
