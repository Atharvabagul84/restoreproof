import Link from "next/link";

export default function TeamSetup() {
  return <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-5 py-12 sm:px-8">
    <Link href="/" className="mb-10 text-xl font-semibold tracking-tight">⌁ Chisel</Link>
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Team workspace setup</p>
    <h1 className="mt-4 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">Your team’s next<br />workspace starts here.</h1>
    <p className="mt-6 max-w-xl text-base leading-7 text-on-surface-variant">Team accounts and shared briefs need a connected Supabase project. Local drafts are ready to use while the workspace is being set up.</p>
    <ol className="mt-8 space-y-4 rounded-2xl border border-outline-variant bg-surface-container p-6 text-sm leading-7">
      <li><span className="mr-3 text-primary">01</span>Create a Supabase project for Chisel.</li>
      <li><span className="mr-3 text-primary">02</span>Apply the supplied workspace database migration.</li>
      <li><span className="mr-3 text-primary">03</span>Connect an SMTP email provider, configure sign-in codes, and add the project URL and publishable key to the app environment.</li>
      <li><span className="mr-3 text-primary">04</span>Restart Chisel, sign in, and create your first workspace.</li>
    </ol>
    <p className="mt-5 text-xs leading-6 text-on-surface-variant">New free Supabase projects need custom SMTP to edit the code email templates. Use the project’s publishable key; the app does not need a service-role key or database password. Follow the Supabase setup guide supplied with this build.</p>
    <div className="mt-8 flex flex-wrap gap-4"><Link href="/" className="rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-on-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">Continue with local drafts</Link><a href="https://supabase.com/dashboard" target="_blank" rel="noreferrer" className="rounded-xl border border-outline-variant px-5 py-3 text-sm focus-visible:outline-2 focus-visible:outline-primary">Open Supabase dashboard ↗</a></div>
  </main>;
}
