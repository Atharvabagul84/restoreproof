import { z } from "zod";
import { assertSameOrigin, privateJson, readJsonBody, RequestInputError, type OriginConfig } from "./auth-request";
export type AuthGateway = { sendCode(email: string): Promise<void>; verifyCode(email: string, token: string): Promise<void>; signOut(): Promise<void> };
const email = z.string().trim().toLowerCase().email().max(254);
const sendSchema = z.strictObject({ email });
const verifySchema = z.strictObject({ email, token: z.string().regex(/^\d{6,10}$/) });
export const createAuthHandler = (
  action: "send-code" | "verify-code" | "signout",
  factory: (() => Promise<AuthGateway>) | null,
  config?: OriginConfig,
) => async (request: Request): Promise<Response> => {
  try {
    assertSameOrigin(request, config);
    if (!factory) throw new RequestInputError(503, "Team sign-in is not connected yet. Follow the Supabase setup guide to enable it.");
    if (action === "signout") {
      await (await factory()).signOut();
      return privateJson({ ok: true });
    }
    const input = await readJsonBody(request);
    if (action === "send-code") {
      const parsed = sendSchema.safeParse(input);
      if (!parsed.success) throw new RequestInputError(400, "Enter a valid email address.");
      await (await factory()).sendCode(parsed.data.email);
      return privateJson({ ok: true, message: "Check your inbox for your sign-in code." });
    }
    const parsed = verifySchema.safeParse(input);
    if (!parsed.success) throw new RequestInputError(400, "Enter your email and the numeric code from your inbox.");
    await (await factory()).verifyCode(parsed.data.email, parsed.data.token);
    return privateJson({ ok: true });
  } catch (error) {
    if (error instanceof RequestInputError) return privateJson({ error: error.message }, error.status);
    return privateJson({ error: action === "verify-code"
      ? "That code could not be verified. Check it or request a new code."
      : "The sign-in service could not complete this request. Please wait a minute and try again." }, action === "verify-code" ? 401 : 502);
  }
};
