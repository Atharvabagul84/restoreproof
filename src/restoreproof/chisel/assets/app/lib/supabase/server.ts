import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { getSupabaseConfig } from "./config";

export const createServerSupabaseClient = async ({ writableCookies = false }: { writableCookies?: boolean } = {}) => {
  const config = getSupabaseConfig();
  if (!config) throw new Error("Supabase is not configured.");
  const cookieStore = await cookies();
  return createServerClient(config.url, config.publishableKey, {
    cookieOptions: { sameSite: "lax", httpOnly: true, secure: process.env.NODE_ENV === "production" },
    global: { fetch: (url, options) => fetch(url, { ...options, cache: "no-store" }) },
    cookies: {
      getAll: () => cookieStore.getAll(),
      setAll: (updates) => {
        if (writableCookies) {
          updates.forEach(({ name, value, options }) => cookieStore.set(name, value, options));
          return;
        }
        // Server Components cannot write cookies; proxy refreshes them before rendering.
        try { updates.forEach(({ name, value, options }) => cookieStore.set(name, value, options)); } catch { /* Read-only render context. */ }
      },
    },
  });
};
