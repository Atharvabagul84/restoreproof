import type { AuthGateway } from "./auth-controller";
export type AuthProvider = {
  signInWithOtp(input: { email: string; options: { shouldCreateUser: boolean } }): Promise<{ error: unknown }>;
  verifyOtp(input: { email: string; token: string; type: "email" }): Promise<{ error: unknown; data: { session: unknown; user: { email_confirmed_at?: string } | null } }>;
  signOut(input: { scope: "local" }): Promise<{ error: unknown }>;
};
export const createSupabaseAuthGateway = (auth: AuthProvider): AuthGateway => ({
  sendCode: async (email) => {
    const { error } = await auth.signInWithOtp({ email, options: { shouldCreateUser: true } });
    if (error) throw error;
  },
  verifyCode: async (email, token) => {
    const { data, error } = await auth.verifyOtp({ email, token, type: "email" });
    if (error || !data.session || !data.user?.email_confirmed_at) throw error ?? new Error("Sign-in did not return a verified session.");
  },
  signOut: async () => {
    const { error } = await auth.signOut({ scope: "local" });
    if (error) throw error;
  },
});
