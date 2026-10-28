import { createServerSupabaseClient } from "../supabase/server";
import { getSupabaseConfig } from "../supabase/config";
import { createTeamHandler, type TeamAction } from "./team-controller";
import { createTeamRepository } from "./team-repository";
import { RequestInputError } from "./auth-request";

const verifiedRepository = async () => {
  const client = await createServerSupabaseClient({ writableCookies: true });
  const { data: { user }, error } = await client.auth.getUser();
  if (error || !user || !user.email_confirmed_at) throw new RequestInputError(401, "Sign in with a verified email to use team workspaces.");
  return createTeamRepository(client, user.id);
};
export const teamRoute = (action: TeamAction) => async (request: Request, context?: { params: Promise<Record<string, string>> }) =>
  createTeamHandler(action, getSupabaseConfig() ? verifiedRepository : null)(request, context ? await context.params : {});
