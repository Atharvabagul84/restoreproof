export class RequestInputError extends Error { constructor(public status: number, message: string) { super(message); } }
export type OriginConfig = { appUrl?: string; production: boolean };
const loopbackHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
const developmentOrigin = (request: Request, normalized: URL): URL => {
  const host = request.headers.get("host");
  if (!host || !loopbackHosts.has(normalized.hostname)) return normalized;
  try {
    const actual = new URL(`${normalized.protocol}//${host}`);
    // Next dev can normalize request.url to localhost even when the browser
    // uses 127.0.0.1. Only accept the real loopback Host on the same port.
    if (actual.host === host && loopbackHosts.has(actual.hostname) && actual.port === normalized.port) return actual;
  } catch { /* Keep the normalized origin for malformed Host headers. */ }
  return normalized;
};
export const assertSameOrigin = (request: Request, config: OriginConfig = {
  appUrl: process.env.CHISEL_APP_URL, production: process.env.NODE_ENV === "production",
}) => {
  if (config.production && !config.appUrl) throw new RequestInputError(503, "The workspace address needs to be configured.");
  let expected: URL;
  try { expected = new URL(config.appUrl || request.url); } catch {
    throw new RequestInputError(503, "The workspace address needs to be configured.");
  }
  if (!["http:", "https:"].includes(expected.protocol) || expected.username || expected.password) {
    throw new RequestInputError(503, "The workspace address needs to be configured.");
  }
  if (!config.production && !config.appUrl) expected = developmentOrigin(request, expected);
  if (request.headers.get("origin") !== expected.origin) {
    throw new RequestInputError(403, "Open Chisel in its own tab and try again.");
  }
};
export const readJsonBody = async (request: Request, maxBytes = 8192): Promise<unknown> => {
  if (request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() !== "application/json") {
    throw new RequestInputError(415, "Send this request as JSON.");
  }
  if (Number(request.headers.get("content-length")) > maxBytes) throw new RequestInputError(413, "This request is too large.");
  const reader = request.body?.getReader();
  if (!reader) throw new RequestInputError(400, "Provide a request body.");
  let bytes = 0;
  let text = "";
  const decoder = new TextDecoder();
  try {
    while (true) {
      const chunk = await reader.read();
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > maxBytes) {
        await reader.cancel();
        throw new RequestInputError(413, "This request is too large.");
      }
      text += decoder.decode(chunk.value, { stream: true });
    }
    text += decoder.decode();
    try { return JSON.parse(text); } catch { throw new RequestInputError(400, "This request contains invalid JSON."); }
  } finally { reader.releaseLock(); }
};
export const privateJson = (body: unknown, status = 200) => Response.json(body, {
  status, headers: { "Cache-Control": "private, no-store", "Referrer-Policy": "no-referrer" },
});
export const safeAuthNext = (value?: string) => value === "/team" || /^\/join\/[a-f0-9]{64}$/.test(value ?? "") ? value! : "/team";
