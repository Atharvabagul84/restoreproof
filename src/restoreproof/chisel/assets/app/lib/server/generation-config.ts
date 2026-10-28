export type GenerationProvider = "anthropic" | "groq";

export interface GenerationConfig {
  apiKey: string;
  model: string;
  production: boolean;
  provider?: GenerationProvider;
  /** Production generation for anonymous visitors, only through the free-tier provider and only with limits. */
  hostedDemo?: boolean;
}

export const providerName = (provider: GenerationProvider = "anthropic") => provider === "groq" ? "Groq" : "Anthropic";
export const providerKeyName = (provider: GenerationProvider = "anthropic") => provider === "groq" ? "GROQ_API_KEY" : "ANTHROPIC_API_KEY";

export const getGenerationConfig = (): GenerationConfig => {
  const provider: GenerationProvider = process.env.CHISEL_GENERATION_PROVIDER?.trim() === "groq" ? "groq" : "anthropic";
  return provider === "groq" ? {
    provider,
    apiKey: process.env.GROQ_API_KEY?.trim() ?? "",
    model: process.env.GROQ_MODEL?.trim() || "openai/gpt-oss-120b",
    production: process.env.NODE_ENV === "production",
    hostedDemo: process.env.CHISEL_HOSTED_DEMO?.trim() === "true",
  } : {
    provider,
    apiKey: process.env.ANTHROPIC_API_KEY?.trim() ?? "",
    model: process.env.ANTHROPIC_MODEL?.trim() || "claude-sonnet-4-6",
    production: process.env.NODE_ENV === "production",
    // Never open paid Anthropic generation to anonymous visitors.
    hostedDemo: false,
  };
};

/** Browser-safe summary for the workspace notice. Contains no keys. */
export const getGenerationSummary = () => {
  const config = getGenerationConfig();
  return { providerName: providerName(config.provider), hostedDemo: Boolean(config.production && config.hostedDemo) };
};
