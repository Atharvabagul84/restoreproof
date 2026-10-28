import type { FeatureDraft } from "../local-drafts";
import type { TeamBrief, WorkspaceDetail, WorkspaceSummary } from "../team/contracts";
import type { OriginConfig } from "./auth-request";
import { assertSameOrigin, privateJson, readJsonBody, RequestInputError } from "./auth-request";
import { executeTeamAction } from "./team-service";
import { ZodError } from "zod";
export interface TeamRepository {
  listWorkspaces(): Promise<WorkspaceSummary[]>;
  getWorkspace(id: string): Promise<WorkspaceDetail>;
  createWorkspace(name: string): Promise<string>;
  saveBrief(workspaceId: string, input: { draft: FeatureDraft; expectedRevision: number }): Promise<TeamBrief>;
  createInvitation(workspaceId: string, email: string, role: "pm" | "engineer", token: string): Promise<string>;
  acceptInvitation(token: string): Promise<string>;
  revokeInvitation(id: string): Promise<void>;
  removeMember(workspaceId: string, userId: string): Promise<void>;
}
export type TeamAction = "list" | "create" | "detail" | "save" | "invite" | "accept" | "revoke" | "remove";
export const createTeamHandler = (action: TeamAction, factory: (() => Promise<TeamRepository>) | null, config?: OriginConfig) => async (request: Request, params: Record<string, string> = {}): Promise<Response> => {
  try {
    const mutation = action !== "list" && action !== "detail";
    if (mutation) assertSameOrigin(request, config);
    if (!factory) throw new RequestInputError(503, "Team workspaces are not connected yet. Complete the Supabase setup first.");
    const repository = await factory();
    const body = mutation && action !== "revoke" && action !== "remove" ? await readJsonBody(request, 262144) : undefined;
    return privateJson(await executeTeamAction(repository, action, params, body), action === "create" || action === "invite" ? 201 : 200);
  } catch (error) {
    if (error instanceof RequestInputError) return privateJson({ error: error.message }, error.status);
    if (error instanceof ZodError) return privateJson({ error: "Check the request fields and try again." }, 400);
    const code = typeof error === "object" && error !== null && "code" in error ? error.code : undefined;
    if (code === "40001" || code === "23505") return privateJson({ error: "A newer revision is already saved. Download your edits, then reload the latest brief before saving again." }, 409);
    if (code === "42501") return privateJson({ error: "You do not have permission to perform this action." }, 403);
    if (code === "22023" && error && typeof error === "object" && "message" in error && typeof error.message === "string" && error.message.startsWith("CHISEL_LIMIT_REACHED")) {
      return privateJson({ error: "This action exceeds a pilot limit: 3 owned workspaces, 25 briefs per workspace, 20 members, or 25 active invitations. Contact the workspace owner." }, 422);
    }
    if (code === "22023") return privateJson({ error: action === "accept" ? "This invitation cannot be accepted. Use the invited email and check that the link is unused, active, and less than seven days old." : "Check the request fields and try again." }, 400);
    if (code === "PGRST116") return privateJson({ error: "This workspace is unavailable or you are no longer a member." }, 404);
    // Deliberately exclude upstream messages, draft content and invite tokens.
    console.error("team_request_failed", { action, code: typeof code === "string" ? code : "unknown" });
    return privateJson({ error: "The workspace could not complete this request. Please try again." }, 502);
  }
};
