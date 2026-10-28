import { createAnthropicCompletion } from "@/lib/server/anthropic-feature-spec";
import { createGenerateSpecHandler } from "@/lib/server/generate-spec-controller";
import { getGenerationConfig } from "@/lib/server/generation-config";
import { createUpstashLimiter } from "@/lib/server/generation-rate-limit";
import { createGroqCompletion } from "@/lib/server/groq-feature-spec";

export const runtime = "nodejs";
export const maxDuration = 60;

export const POST = async (request: Request) => {
  const config = getGenerationConfig();
  const complete = config.provider === "groq" ? createGroqCompletion(config.apiKey) : createAnthropicCompletion(config.apiKey);
  return createGenerateSpecHandler({ config, complete, limiter: createUpstashLimiter() })(request);
};
