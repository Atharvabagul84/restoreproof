"use client";

import { VISITOR_DAILY_LIMIT } from "../lib/demo-limits";
import FeatureReview from "./FeatureReview";
import { useFeatureWorkspace } from "./useFeatureWorkspace";

const secondaryButton = "rounded-xl border border-outline-variant bg-surface-container px-4 py-2.5 text-sm font-medium text-on-surface transition hover:border-primary/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-40";
const primaryButton = "rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-on-primary transition hover:bg-primary-fixed-dim focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-40";

export default function FeatureWorkspace({ generation }: { generation: { providerName: string; hostedDemo: boolean } }) {
  const workspace = useFeatureWorkspace();
  const { draft, busy } = workspace;
  return (
    <div className="min-h-screen bg-background text-on-surface">
      <a href="#workspace" className="sr-only focus:not-sr-only focus:block focus:p-3">Skip to workspace</a>
      <header className="border-b border-outline-variant bg-surface-container-low">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-8">
          <div className="flex items-center gap-3"><span aria-hidden className="flex size-9 items-center justify-center rounded-xl bg-primary text-xl font-bold text-on-primary">⌁</span><span className="text-xl font-semibold tracking-tight">Chisel</span><span className="ml-2 rounded-full border border-outline-variant px-2.5 py-1 text-xs text-on-surface-variant">Local MVP</span></div>
          <div className="flex items-center gap-4"><a href="/team" className="text-sm text-primary underline underline-offset-4">Team workspace ↗</a><button className={secondaryButton} onClick={workspace.newBrief}>+ New brief</button></div>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1440px] gap-8 px-5 py-8 sm:px-8 lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-12">
        <aside aria-label="Saved drafts" className="space-y-7">
          <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Your workspace</p><h2 className="mt-3 text-lg font-semibold">Feature drafts <span className="text-sm text-on-surface-variant">{workspace.drafts.length}</span></h2><p className="mt-2 text-xs leading-5 text-on-surface-variant">Saved on this browser only. Download a copy to share with your team.</p></div>
          <div className="flex gap-3 overflow-x-auto lg:block lg:space-y-3">
            {workspace.drafts.length === 0 && <p className="rounded-xl border border-dashed border-outline px-4 py-5 text-sm leading-6 text-on-surface-variant">Your saved specs will appear here.</p>}
            {workspace.drafts.map((item) => <div key={item.id} className={`min-w-48 rounded-xl border p-3 lg:min-w-0 ${draft?.id === item.id ? "border-primary/50 bg-primary/5" : "border-outline-variant bg-surface-container"}`}><button onClick={() => workspace.reopen(item)} className="w-full text-left text-sm font-medium focus-visible:outline-2 focus-visible:outline-primary">{item.spec.title}<span className="mt-2 block text-xs font-normal text-on-surface-variant">Revision {item.revision} · {item.source === "example" ? "Example" : item.source === "ai" ? "AI draft" : "Manual"}</span></button><button onClick={() => workspace.remove(item.id)} className="mt-3 text-xs text-on-surface-variant underline underline-offset-4 hover:text-red-300" aria-label={`Remove ${item.spec.title}`}>Remove</button></div>)}
          </div>
          <div className="hidden rounded-xl bg-surface-container px-4 py-4 text-xs leading-6 text-on-surface-variant lg:block">A good handoff makes the unknowns visible.<br /><span className="text-on-surface">Brief. Scope. Questions. Criteria.</span></div>
        </aside>
        <main id="workspace" className="min-w-0 pb-16">
          <div className="mb-7 flex flex-wrap items-center gap-3 text-xs font-medium text-on-surface-variant"><span className={!draft ? "text-primary" : ""}>01 &nbsp; Capture</span><span aria-hidden>—</span><span className={draft ? "text-primary" : ""}>02 &nbsp; Review</span><span aria-hidden>—</span><span>03 &nbsp; Handoff</span></div>
          {workspace.error && <div role="alert" className="mb-6 rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-sm leading-6 text-red-200">{workspace.error}</div>}
          {workspace.notice && <div role="status" className="mb-6 rounded-xl border border-tertiary/25 bg-tertiary/5 p-4 text-sm leading-6 text-tertiary-fixed">{workspace.notice}</div>}
          {!draft ? <>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">From discovery to delivery</p>
            <h1 className="mt-4 max-w-2xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">Make the next feature<br className="hidden sm:block" /> clear enough to build.</h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-on-surface-variant">Bring your customer notes, product ideas, and constraints. Shape them into a feature brief your PM and engineering team can review together.</p>
            <form onSubmit={(event) => { event.preventDefault(); void workspace.generate(); }} className="mt-8 rounded-2xl border border-outline-variant bg-surface-container p-5 sm:p-7">
              <label htmlFor="source-brief" className="text-sm font-semibold">What are we building, and why?</label>
              <p id="brief-help" className="mt-2 text-xs leading-6 text-on-surface-variant">Include the user, problem, desired outcome, constraints, and anything you already know is out of scope.</p>
              <textarea id="source-brief" aria-describedby="brief-help brief-count" disabled={busy} value={workspace.note} onChange={(event) => workspace.setNote(event.target.value)} maxLength={12000} rows={9} placeholder="Our support leads spend every Friday copying ticket data into spreadsheets. We want…" className="mt-5 w-full resize-y rounded-xl border border-outline-variant bg-background p-4 text-sm leading-7 placeholder:text-on-surface-variant focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-60" />
              <div className="mt-3 flex flex-wrap justify-between gap-3 text-xs text-on-surface-variant"><span>Paste text or a transcript · 30 characters minimum</span><span id="brief-count">{workspace.note.length.toLocaleString()} / 12,000</span></div>
              <div className="mt-6 flex flex-wrap items-center gap-3"><button disabled={busy || workspace.note.trim().length < 30} className={primaryButton}>{busy ? "Generating draft…" : "Generate feature spec"}</button>{busy ? <button type="button" onClick={workspace.cancel} className={secondaryButton}>Cancel</button> : <button type="button" onClick={workspace.manual} className={secondaryButton}>Write manually</button>}</div>
              {generation.hostedDemo
                ? <p className="mt-4 text-xs leading-6 text-on-surface-variant">Demo drafts use a free model on Groq, so don’t paste confidential information. {VISITOR_DAILY_LIMIT} drafts per visitor per day{workspace.remaining === null ? "" : ` · ${workspace.remaining} left today`}. Manual writing and the example are unlimited.</p>
                : <p className="mt-4 text-xs leading-6 text-on-surface-variant">AI generation uses the server’s configured model. Your brief is sent to {generation.providerName} when you generate. Manual writing and the example work without an API key.</p>}
              {busy && <p role="status" className="mt-3 text-sm text-primary">Drafting scope, stories, and questions. You can cancel and keep your brief.</p>}
            </form>
            <button type="button" onClick={workspace.example} disabled={busy} className="mt-5 flex w-full items-center justify-between gap-4 rounded-2xl border border-outline-variant p-5 text-left transition hover:border-primary/50 disabled:opacity-40"><div><span className="text-sm font-medium">Explore a worked example</span><p className="mt-1 text-xs leading-6 text-on-surface-variant">Filtered ticket exports · Scope, edge cases, and unanswered questions</p></div><span aria-hidden className="text-primary">↗</span></button>
          </> : <>
            <div className="mb-6"><div className="flex flex-wrap items-center gap-2 text-xs"><span className="rounded-full bg-primary/10 px-3 py-1 text-primary">{draft.source === "example" ? "Worked example · not AI generated" : draft.source === "ai" ? "AI draft · needs review" : "Manual draft"}</span><span className="text-on-surface-variant">{workspace.dirty ? "Unsaved changes" : `Saved revision ${draft.revision}`}</span></div><h1 className="mt-4 text-3xl font-semibold tracking-tight">Review the feature spec</h1><p className="mt-2 text-sm leading-6 text-on-surface-variant">Edit every detail. Keep unanswered questions visible. Review marks are personal checks, not team approval.</p></div>
            <div className="sticky top-0 z-10 mb-6 flex flex-wrap items-center gap-2 rounded-xl border border-outline-variant bg-background/95 p-3 backdrop-blur"><button className={primaryButton} onClick={workspace.save}>Save draft</button><button className={secondaryButton} onClick={() => void workspace.exportDraft("markdown")}>Download .md</button><button className={secondaryButton} onClick={() => void workspace.exportDraft("copy")}>Copy Markdown</button><button className={secondaryButton} onClick={() => void workspace.exportDraft("json")}>Export JSON</button></div>
            <details className="mb-6 rounded-xl border border-outline-variant p-4"><summary className="cursor-pointer text-sm font-medium">Original brief</summary><p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-on-surface-variant">{draft.note || "Started as a manual draft."}</p></details>
            <FeatureReview key={draft.id} spec={draft.spec} onChange={workspace.updateSpec} checkedIds={draft.checkedIds} onCheckedChange={workspace.updateChecks} />
          </>}
        </main>
      </div>
    </div>
  );
}
