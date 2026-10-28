export class TeamRequestError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

export const teamRequest = async <T>(path: string, options?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    ...options, cache: "no-store", credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) throw new TeamRequestError(typeof result?.error === "string" ? result.error : "The workspace could not be reached. Please try again.", response.status);
  return result as T;
};

export const teamError = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";
export const teamPrimary = "rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-on-primary transition hover:bg-primary-fixed-dim focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-40";
export const teamSecondary = "rounded-xl border border-outline-variant bg-surface-container px-4 py-2.5 text-sm font-medium text-on-surface transition hover:border-primary/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-40";
export const teamInput = "w-full rounded-xl border border-outline-variant bg-background p-3 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:opacity-50";
