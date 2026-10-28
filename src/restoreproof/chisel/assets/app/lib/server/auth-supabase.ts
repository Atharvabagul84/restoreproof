import { createServerSupabaseClient } from "../supabase/server";
import type { AuthGateway } from "./auth-controller";
import { createSupabaseAuthGateway } from "./auth-service";

export const createAuthGateway = async (): Promise<AuthGateway> => {
  const client = await createServerSupabaseClient({ writableCookies: true });
  return createSupabaseAuthGateway(client.auth);
};
