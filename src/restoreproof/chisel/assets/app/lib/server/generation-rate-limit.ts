import { createHash } from "node:crypto";
import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";
import { GLOBAL_DAILY_LIMIT, VISITOR_DAILY_LIMIT } from "../demo-limits";

export { GLOBAL_DAILY_LIMIT, VISITOR_DAILY_LIMIT };

export type LimitResult =
  | { allowed: true; remaining: number }
  | { allowed: false; scope: "visitor" | "global"; reset: number };

/** Throws when the limit store cannot answer; callers must fail closed. */
export type GenerationLimiter = (visitorId: string) => Promise<LimitResult>;

export class LimiterUnavailableError extends Error {
  constructor() { super("The usage-limit store did not answer."); this.name = "LimiterUnavailableError"; }
}

// Vercel overwrites x-forwarded-for with the real client address, so the first entry is trusted there.
export const visitorId = (request: Request, salt: string) => {
  const ip = request.headers.get("x-forwarded-for")?.split(",", 1)[0].trim() || request.headers.get("x-real-ip")?.trim() || "unknown";
  return createHash("sha256").update(`${salt}:${ip}`).digest("hex");
};

type Check = (identifier: string) => Promise<{ success: boolean; remaining: number; reset: number; reason?: string }>;

export const createLimiter = (checks: { visitor: Check; global: Check }): GenerationLimiter => async (id) => {
  const read = async (check: Check, identifier: string) => {
    let result;
    try { result = await check(identifier); } catch { throw new LimiterUnavailableError(); }
    // Upstash allows the request when Redis is slow ("timeout"); treat that as no answer.
    if (result.reason === "timeout") throw new LimiterUnavailableError();
    return result;
  };
  // Visitor first, so one visitor over their limit can't spend the shared daily budget.
  const visitor = await read(checks.visitor, id);
  if (!visitor.success) return { allowed: false, scope: "visitor", reset: visitor.reset };
  const global = await read(checks.global, "all");
  if (!global.success) return { allowed: false, scope: "global", reset: global.reset };
  return { allowed: true, remaining: visitor.remaining };
};

/** Returns null unless every Upstash setting is present, which keeps hosted generation closed. */
export const createUpstashLimiter = (env: NodeJS.ProcessEnv = process.env): { limit: GenerationLimiter; salt: string } | null => {
  const url = env.UPSTASH_REDIS_REST_URL?.trim();
  const token = env.UPSTASH_REDIS_REST_TOKEN?.trim();
  const salt = env.CHISEL_VISITOR_SALT?.trim();
  if (!url || !token || !salt) return null;
  const redis = new Redis({ url, token });
  const visitor = new Ratelimit({ redis, prefix: "chisel:demo:visitor", limiter: Ratelimit.fixedWindow(VISITOR_DAILY_LIMIT, "1 d"), analytics: false });
  const global = new Ratelimit({ redis, prefix: "chisel:demo:global", limiter: Ratelimit.fixedWindow(GLOBAL_DAILY_LIMIT, "1 d"), analytics: false });
  return { limit: createLimiter({ visitor: (id) => visitor.limit(id), global: (id) => global.limit(id) }), salt };
};
