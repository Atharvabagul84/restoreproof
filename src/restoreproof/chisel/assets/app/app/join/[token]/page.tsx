import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import JoinWorkspace from "../../../components/team/JoinWorkspace";
import TeamSetup from "../../../components/team/TeamSetup";
import { getSupabaseConfig } from "../../../lib/supabase/config";
import { createServerSupabaseClient } from "../../../lib/supabase/server";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { referrer: "no-referrer", robots: { index: false, follow: false } };

export default async function JoinPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  if (!/^[a-f0-9]{64}$/.test(token)) return <main className="mx-auto max-w-2xl px-5 py-20"><h1 className="text-3xl font-semibold">This invitation link is incomplete.</h1><p className="mt-5 text-on-surface-variant">Ask your workspace owner to share a new link.</p><Link href="/team" className="mt-6 inline-block text-primary underline">Go to your workspaces</Link></main>;
  if (!getSupabaseConfig()) return <TeamSetup />;
  const supabase = await createServerSupabaseClient();
  const { data: { user }, error } = await supabase.auth.getUser();
  if (error || !user?.email || !user.email_confirmed_at) redirect(`/login?next=${encodeURIComponent(`/join/${token}`)}`);
  return <JoinWorkspace token={token} email={user.email} />;
}
