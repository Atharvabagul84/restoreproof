import { z } from "zod";
import type { CompleteFeatureSpec } from "./feature-spec-generation";

const GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions";

// Only the fields Chisel reads; Groq's OpenAI-compatible response carries more.
const groqResponseSchema = z.object({
  choices: z.array(z.object({
    message: z.object({ content: z.string().nullable().optional() }),
    finish_reason: z.string().nullable(),
  })).min(1),
});

export class ProviderHttpError extends Error {
  constructor(public readonly status: number) {
    super(`Generation provider returned HTTP ${status}`);
    this.name = "ProviderHttpError";
  }
}

export const createGroqCompletion = (apiKey: string, fetchImpl: typeof fetch = fetch): CompleteFeatureSpec => async (request) => {
  const response = await fetchImpl(GROQ_CHAT_URL, {
    method: "POST",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: request.model,
      messages: [{ role: "system", content: request.system }, { role: "user", content: request.note }],
      response_format: { type: "json_object" },
      max_completion_tokens: 8192,
    }),
    signal: request.signal,
  });
  // Status only: provider error bodies can echo the request and never reach logs or users.
  if (!response.ok) throw new ProviderHttpError(response.status);
  const choice = groqResponseSchema.parse(await response.json()).choices[0];
  return {
    text: choice.message.content ?? "",
    // Map OpenAI-style "stop" onto the service's clean-finish check; "length" stays truncated.
    stopReason: choice.finish_reason === "stop" ? "end_turn" : choice.finish_reason,
  };
};
