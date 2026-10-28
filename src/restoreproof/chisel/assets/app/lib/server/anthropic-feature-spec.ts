import Anthropic from "@anthropic-ai/sdk";
import type { CompleteFeatureSpec } from "./feature-spec-generation";

export const createAnthropicCompletion = (apiKey: string): CompleteFeatureSpec => async (request) => {
  const client = new Anthropic({ apiKey, timeout: 45000, maxRetries: 0 });
  const message = await client.messages.create({
    model: request.model,
    max_tokens: 8192,
    system: request.system,
    messages: [{ role: "user", content: request.note }],
  }, { signal: request.signal });
  return {
    text: message.content.filter((block) => block.type === "text").map((block) => block.text).join("\n"),
    stopReason: message.stop_reason,
  };
};
