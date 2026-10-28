export type SupabaseConfig = { url: string; publishableKey: string };
export const readSupabaseConfig = (url?: string, publishableKey?: string): SupabaseConfig | null => {
  if (!url?.trim() || !publishableKey?.trim().startsWith("sb_publishable_")) return null;
  try {
    const parsed = new URL(url.trim());
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname);
    if ((parsed.protocol !== "https:" && !(local && parsed.protocol === "http:")) || parsed.username || parsed.password || parsed.search || parsed.hash || parsed.pathname !== "/") return null;
    return { url: parsed.origin, publishableKey: publishableKey.trim() };
  } catch { return null; }
};
export const getSupabaseConfig = (): SupabaseConfig | null => readSupabaseConfig(
  process.env.NEXT_PUBLIC_SUPABASE_URL, process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY,
);
