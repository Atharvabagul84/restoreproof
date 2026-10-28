import { redirect } from "next/navigation";
import TeamWorkspace from "../../components/team/TeamWorkspace";
import TeamSetup from "../../components/team/TeamSetup";
import { getSupabaseConfig } from "../../lib/supabase/config";
import { createServerSupabaseClient } from "../../lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function TeamPage({ searchParams }: { searchParams: Promise<{ workspace?: string }> }) {
  if (!getSupabaseConfig()) return <TeamSetup />;
  const supabase = await createServerSupabaseClient();
  const { data: { user }, error } = await supabase.auth.getUser();
  if (error || !user?.email || !user.email_confirmed_at) redirect("/login?next=/team");
  const { workspace } = await searchParams;
  const initialWorkspace = typeof workspace === "string" && /^[0-9a-f-]{36}$/i.test(workspace) ? workspace : undefined;
  return <TeamWorkspace email={user.email} initialWorkspace={initialWorkspace} />;
}
