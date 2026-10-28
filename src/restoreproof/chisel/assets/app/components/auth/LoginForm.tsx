"use client";

import { useState, type FormEvent } from "react";

export default function LoginForm({ next }: { next: string }) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await fetch(`/api/auth/${sent ? "verify-code" : "send-code"}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sent ? { email, token } : { email }),
      });
      const result: { error?: string } = await response.json();
      if (!response.ok) throw new Error(result.error || "Sign-in could not be completed. Please try again.");
      if (sent) { window.location.assign(next); return; }
      setSent(true);
      setMessage("Check your inbox for your sign-in code. It may take a minute to arrive.");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Sign-in could not be completed. Please try again.");
    } finally { setBusy(false); }
  };

  return (
    <form onSubmit={submit} className="mt-8 space-y-5 rounded-2xl border border-white/10 bg-white/[0.025] p-6">
      <div>
        <label htmlFor="login-email" className="block text-sm font-medium">Work email</label>
        <input id="login-email" type="email" autoComplete="email" required maxLength={254} value={email} disabled={sent || busy} onChange={(event) => setEmail(event.target.value)} className="mt-2 w-full rounded-lg border border-white/15 bg-zinc-950 px-3 py-2.5 text-sm outline-none focus:border-violet-400 disabled:text-zinc-400" placeholder="you@company.com" />
      </div>
      {sent && <div>
        <label htmlFor="login-code" className="block text-sm font-medium">Sign-in code</label>
        <input id="login-code" type="text" inputMode="numeric" autoComplete="one-time-code" required pattern="[0-9]{6,10}" minLength={6} maxLength={10} value={token} disabled={busy} onChange={(event) => setToken(event.target.value)} className="mt-2 w-full rounded-lg border border-white/15 bg-zinc-950 px-3 py-2.5 font-mono tracking-widest outline-none focus:border-violet-400" placeholder="123456" />
      </div>}
      {message && <p role="status" className="text-sm leading-6 text-emerald-300">{message}</p>}
      {error && <p role="alert" className="text-sm leading-6 text-rose-300">{error}</p>}
      <button type="submit" disabled={busy} className="w-full rounded-lg bg-violet-400 px-4 py-3 text-sm font-semibold text-zinc-950 hover:bg-violet-300 disabled:opacity-50">{busy ? "Please wait…" : sent ? "Verify and continue" : "Email me a sign-in code"}</button>
      {sent ? <button type="button" disabled={busy} onClick={() => { setSent(false); setToken(""); setError(""); setMessage(""); }} className="text-sm text-violet-300 hover:text-violet-200">Use another email or request a new code</button> : <p className="text-xs leading-5 text-zinc-500">Your first sign-in creates an account. Team access is granted through an invitation or by creating your own workspace.</p>}
    </form>
  );
}
