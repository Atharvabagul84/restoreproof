import Link from "next/link";
import { redirect } from "next/navigation";
import LoginForm from "@/components/auth/LoginForm";
import { getSupabaseConfig } from "@/lib/supabase/config";
import { createServerSupabaseClient } from "@/lib/supabase/server";
import { safeAuthNext } from "@/lib/server/auth-request";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const query = await searchParams;
  const next = safeAuthNext(typeof query.next === "string" ? query.next : undefined);
  const configured = Boolean(getSupabaseConfig());
  if (configured) {
    const client = await createServerSupabaseClient();
    const { data, error } = await client.auth.getUser();
    if (!error && data.user?.email_confirmed_at) redirect(next);
  }
  return (
    <main className="min-h-screen bg-[#09090b] px-6 py-16 text-zinc-100">
      <div className="mx-auto max-w-md">
        <Link href="/" className="text-sm text-violet-300 hover:text-violet-200">← Local workspace</Link>
        <div className="mt-12 text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">Chisel · Team workspace</div>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight">A shared place for your next feature.</h1>
        <p className="mt-4 text-sm leading-6 text-zinc-400">Sign in to save briefs with your team, invite a product manager or engineer, and pick up where you left off.</p>
        {configured ? <LoginForm next={next} /> : (
          <section className="mt-8 rounded-2xl border border-violet-400/20 bg-violet-400/5 p-6">
            <h2 className="font-medium">Team sign-in is ready to connect</h2>
            <p className="mt-3 text-sm leading-6 text-zinc-400">Create your Supabase project and follow the included setup guide to enable accounts and shared storage. You can keep drafting in the local workspace while it is being connected.</p>
            <Link href="/" className="mt-5 inline-block rounded-lg bg-violet-400 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-violet-300">Continue locally</Link>
          </section>
        )}
      </div>
    </main>
  );
}
