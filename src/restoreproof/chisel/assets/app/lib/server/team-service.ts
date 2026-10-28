import { randomBytes } from "node:crypto";
import { acceptInvitationInput, invitationInput, saveBriefInput, uuidSchema, workspaceInput } from "../team/contracts";
import type { TeamAction, TeamRepository } from "./team-controller";

export const executeTeamAction = async (repository: TeamRepository, action: TeamAction, params: Record<string, string>, body: unknown) => {
  if (action === "list") return { workspaces: await repository.listWorkspaces() };
  if (action === "create") return { id: await repository.createWorkspace(workspaceInput.parse(body).name) };
  if (action === "accept") return { workspaceId: await repository.acceptInvitation(acceptInvitationInput.parse(body).token) };
  if (action === "revoke") {
    await repository.revokeInvitation(uuidSchema.parse(params.invitationId));
    return { ok: true };
  }
  const workspaceId = uuidSchema.parse(params.workspaceId);
  if (action === "detail") return repository.getWorkspace(workspaceId);
  if (action === "save") return { brief: await repository.saveBrief(workspaceId, saveBriefInput.parse(body)) };
  if (action === "remove") {
    await repository.removeMember(workspaceId, uuidSchema.parse(params.userId));
    return { ok: true };
  }
  const input = invitationInput.parse(body);
  const token = randomBytes(32).toString("hex");
  const id = await repository.createInvitation(workspaceId, input.email, input.role, token);
  return { id, invitePath: `/join/${token}` };
};
