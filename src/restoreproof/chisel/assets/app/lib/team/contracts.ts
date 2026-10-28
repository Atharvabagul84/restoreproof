import { z } from "zod";
import { draftSchema, type FeatureDraft } from "../local-drafts";

export type TeamRole = "owner" | "pm" | "engineer";
export type WorkspaceSummary = { id: string; name: string; role: TeamRole; createdAt: string };
export type TeamMember = { userId: string; email: string; role: TeamRole; joinedAt: string };
export type TeamInvitation = { id: string; email: string; role: "pm" | "engineer"; expiresAt: string; acceptedAt: string | null; revokedAt: string | null };
export type TeamBrief = { id: string; workspaceId: string; draft: FeatureDraft; revision: number; updatedAt: string; updatedBy: string };
export type WorkspaceDetail = { workspace: WorkspaceSummary; members: TeamMember[]; invitations: TeamInvitation[]; briefs: TeamBrief[] };
export const uuidSchema = z.uuid();
export const workspaceInput = z.strictObject({ name: z.string().trim().min(1).max(100) });
export const invitationInput = z.strictObject({ email: z.string().trim().toLowerCase().email().max(254), role: z.enum(["pm", "engineer"]) });
export const acceptInvitationInput = z.strictObject({ token: z.string().regex(/^[a-f0-9]{64}$/) });
export const saveBriefInput = z.strictObject({ draft: draftSchema.safeExtend({ id: uuidSchema }), expectedRevision: z.number().int().min(0).max(2147483646) });
