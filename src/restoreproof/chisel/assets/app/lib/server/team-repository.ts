import type { SupabaseClient } from "@supabase/supabase-js";
import { z } from "zod";
import { draftSchema } from "../local-drafts";
import type { TeamBrief, TeamRole, WorkspaceDetail } from "../team/contracts";
import type { TeamRepository } from "./team-controller";
import { RequestInputError } from "./auth-request";

const briefRow = z.object({ id: z.string(), workspace_id: z.string(), draft: draftSchema, revision: z.number(), updated_at: z.string(), updated_by: z.string() });
const mapBrief = (value: unknown): TeamBrief => {
  const row = briefRow.parse(value);
  return { id: row.id, workspaceId: row.workspace_id, draft: row.draft, revision: row.revision, updatedAt: row.updated_at, updatedBy: row.updated_by };
};
const checked = <T>(result: { data: T; error: unknown }): T => {
  if (result.error) throw result.error;
  return result.data;
};

export const createTeamRepository = (client: SupabaseClient, userId: string): TeamRepository => {
  const rpc = async (name: string, args: Record<string, unknown>) => checked(await client.rpc(name, args));
  return {
    listWorkspaces: async () => {
      const memberships = checked(await client.from("chisel_members").select("workspace_id,role").eq("user_id", userId)) ?? [];
      if (!memberships.length) return [];
      const rows = checked(await client.from("chisel_workspaces").select("id,name,created_at").in("id", memberships.map((item) => item.workspace_id)).order("created_at", { ascending: true })) ?? [];
      return rows.map((row) => ({ id: row.id, name: row.name, createdAt: row.created_at, role: memberships.find((member) => member.workspace_id === row.id)!.role as TeamRole }));
    },
    getWorkspace: async (id): Promise<WorkspaceDetail> => {
      const workspace = checked(await client.from("chisel_workspaces").select("id,name,created_at").eq("id", id).single());
      if (!workspace) throw new RequestInputError(404, "This workspace is unavailable or you are no longer a member.");
      const results = await Promise.all([
        client.from("chisel_members").select("user_id,email,role,joined_at").eq("workspace_id", id).order("joined_at"),
        client.from("chisel_briefs").select("id,workspace_id,draft,revision,updated_at,updated_by").eq("workspace_id", id).order("updated_at", { ascending: false }),
        client.from("chisel_invitations").select("id,email,role,expires_at,accepted_at,revoked_at").eq("workspace_id", id).order("expires_at", { ascending: false }).limit(100),
      ]);
      const members = checked(results[0]) ?? [];
      const self = members.find((member) => member.user_id === userId);
      if (!self) throw new RequestInputError(404, "This workspace is unavailable or you are no longer a member.");
      return {
        workspace: { id: workspace.id, name: workspace.name, role: self.role as TeamRole, createdAt: workspace.created_at },
        members: members.map((row) => ({ userId: row.user_id, email: row.email, role: row.role as TeamRole, joinedAt: row.joined_at })),
        briefs: (checked(results[1]) ?? []).map(mapBrief),
        invitations: (checked(results[2]) ?? []).map((row) => ({ id: row.id, email: row.email, role: row.role as "pm" | "engineer", expiresAt: row.expires_at, acceptedAt: row.accepted_at, revokedAt: row.revoked_at })),
      };
    },
    createWorkspace: async (name) => rpc("chisel_create_workspace", { p_name: name }),
    saveBrief: async (workspaceId, input) => mapBrief(await rpc("chisel_save_brief", { p_workspace_id: workspaceId, p_brief_id: input.draft.id, p_expected_revision: input.expectedRevision, p_draft: input.draft })),
    createInvitation: async (workspaceId, email, role, token) => rpc("chisel_create_invitation", { p_workspace_id: workspaceId, p_email: email, p_role: role, p_token: token }),
    acceptInvitation: async (token) => rpc("chisel_accept_invitation", { p_token: token }),
    revokeInvitation: async (id) => { await rpc("chisel_revoke_invitation", { p_invitation_id: id }); },
    removeMember: async (workspaceId, userId) => { await rpc("chisel_remove_member", { p_workspace_id: workspaceId, p_user_id: userId }); },
  };
};
