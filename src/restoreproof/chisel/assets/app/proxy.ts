import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";
import { getSupabaseConfig } from "./lib/supabase/config";

export async function proxy(request: NextRequest) {
  let response = NextResponse.next({ request });
  const config = getSupabaseConfig();
  if (config) {
    const client = createServerClient(config.url, config.publishableKey, {
      cookieOptions: { sameSite: "lax", httpOnly: true, secure: process.env.NODE_ENV === "production" },
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (updates) => {
          updates.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          updates.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    });
    // Fresh identity verification also refreshes expired cookies. Protected routes verify again.
    await client.auth.getUser();
  }
  response.headers.set("Cache-Control", "private, no-store");
  response.headers.set("Referrer-Policy", "no-referrer");
  return response;
}

export const config = { matcher: ["/login", "/team/:path*", "/join/:path*"] };
