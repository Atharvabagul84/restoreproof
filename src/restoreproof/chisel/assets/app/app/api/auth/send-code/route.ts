import { createAuthHandler } from "@/lib/server/auth-controller";
import { createAuthGateway } from "@/lib/server/auth-supabase";
import { getSupabaseConfig } from "@/lib/supabase/config";

export const POST = (request: Request) => createAuthHandler("send-code", getSupabaseConfig() ? createAuthGateway : null)(request);
