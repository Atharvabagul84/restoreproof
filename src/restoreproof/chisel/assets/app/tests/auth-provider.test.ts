import assert from "node:assert/strict";
import { test } from "node:test";
import { createSupabaseAuthGateway, type AuthProvider } from "../lib/server/auth-service";

const provider = (): AuthProvider => ({
  signInWithOtp: async () => ({ error: null }),
  verifyOtp: async () => ({ data: { session: {}, user: { email_confirmed_at: "2026-10-06T00:00:00Z" } }, error: null }),
  signOut: async () => ({ error: null }),
});

test("email OTP sign-in allows first-time users without a password", async () => {
  const auth = provider(); let received: unknown;
  auth.signInWithOtp = async (input) => { received = input; return { error: null }; };
  await createSupabaseAuthGateway(auth).sendCode("pm@example.com");
  assert.deepEqual(received, { email: "pm@example.com", options: { shouldCreateUser: true } });
});
test("an unconfirmed user or missing session cannot complete sign-in", async () => {
  const auth = provider();
  auth.verifyOtp = async () => ({ data: { user: { email_confirmed_at: undefined }, session: {} }, error: null });
  await assert.rejects(createSupabaseAuthGateway(auth).verifyCode("pm@example.com", "123456"));
  auth.verifyOtp = async () => ({ data: { user: { email_confirmed_at: "2026-10-06T00:00:00Z" }, session: null }, error: null });
  await assert.rejects(createSupabaseAuthGateway(auth).verifyCode("pm@example.com", "123456"));
});
test("OTP errors are never reported as a successful session", async () => {
  const auth = provider();
  auth.verifyOtp = async () => ({ data: { user: null, session: null }, error: new Error("expired token") });
  await assert.rejects(createSupabaseAuthGateway(auth).verifyCode("pm@example.com", "123456"));
});
test("signout ends the current browser session without revoking other devices", async () => {
  const auth = provider(); let received: unknown;
  auth.signOut = async (input) => { received = input; return { error: null }; };
  await createSupabaseAuthGateway(auth).signOut();
  assert.deepEqual(received, { scope: "local" });
});
