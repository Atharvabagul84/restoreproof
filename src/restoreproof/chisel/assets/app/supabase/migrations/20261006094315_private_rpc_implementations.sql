-- Keep the RPC interface stable while removing privileged implementations
-- from the exposed public schema. chisel_private must remain unexposed in the
-- Supabase Data API settings. Every implementation retains its verified-user,
-- workspace authorization, input validation, and transaction checks.
begin;

alter function public.chisel_create_workspace(text) set schema chisel_private;
alter function public.chisel_create_invitation(uuid, text, text, text) set schema chisel_private;
alter function public.chisel_accept_invitation(text) set schema chisel_private;
alter function public.chisel_revoke_invitation(uuid) set schema chisel_private;
alter function public.chisel_remove_member(uuid, uuid) set schema chisel_private;
alter function public.chisel_save_brief(uuid, uuid, integer, jsonb) set schema chisel_private;

create function public.chisel_create_workspace(p_name text) returns uuid
language sql security invoker set search_path = '' as $$
  select chisel_private.chisel_create_workspace(p_name);
$$;

create function public.chisel_create_invitation(p_workspace_id uuid, p_email text, p_role text, p_token text) returns uuid
language sql security invoker set search_path = '' as $$
  select chisel_private.chisel_create_invitation(p_workspace_id, p_email, p_role, p_token);
$$;

create function public.chisel_accept_invitation(p_token text) returns uuid
language sql security invoker set search_path = '' as $$
  select chisel_private.chisel_accept_invitation(p_token);
$$;

create function public.chisel_revoke_invitation(p_invitation_id uuid) returns void
language sql security invoker set search_path = '' as $$
  select chisel_private.chisel_revoke_invitation(p_invitation_id);
$$;

create function public.chisel_remove_member(p_workspace_id uuid, p_user_id uuid) returns void
language sql security invoker set search_path = '' as $$
  select chisel_private.chisel_remove_member(p_workspace_id, p_user_id);
$$;

create function public.chisel_save_brief(p_workspace_id uuid, p_brief_id uuid, p_expected_revision integer, p_draft jsonb) returns jsonb
language sql security invoker set search_path = '' as $$
  select chisel_private.chisel_save_brief(p_workspace_id, p_brief_id, p_expected_revision, p_draft);
$$;

-- Invoker wrappers need only EXECUTE on their private implementations. They
-- confer no direct table write privileges and never change the caller identity.
revoke all on function
  public.chisel_create_workspace(text), public.chisel_create_invitation(uuid, text, text, text),
  public.chisel_accept_invitation(text), public.chisel_revoke_invitation(uuid),
  public.chisel_remove_member(uuid, uuid), public.chisel_save_brief(uuid, uuid, integer, jsonb),
  chisel_private.chisel_create_workspace(text), chisel_private.chisel_create_invitation(uuid, text, text, text),
  chisel_private.chisel_accept_invitation(text), chisel_private.chisel_revoke_invitation(uuid),
  chisel_private.chisel_remove_member(uuid, uuid), chisel_private.chisel_save_brief(uuid, uuid, integer, jsonb)
  from public, anon, authenticated;
grant execute on function
  public.chisel_create_workspace(text), public.chisel_create_invitation(uuid, text, text, text),
  public.chisel_accept_invitation(text), public.chisel_revoke_invitation(uuid),
  public.chisel_remove_member(uuid, uuid), public.chisel_save_brief(uuid, uuid, integer, jsonb),
  chisel_private.chisel_create_workspace(text), chisel_private.chisel_create_invitation(uuid, text, text, text),
  chisel_private.chisel_accept_invitation(text), chisel_private.chisel_revoke_invitation(uuid),
  chisel_private.chisel_remove_member(uuid, uuid), chisel_private.chisel_save_brief(uuid, uuid, integer, jsonb)
  to authenticated;

create index chisel_brief_versions_creator_idx on public.chisel_brief_versions(created_by);
create index chisel_briefs_updater_idx on public.chisel_briefs(updated_by);
create index chisel_invitations_creator_idx on public.chisel_invitations(created_by);

notify pgrst, 'reload schema';
commit;
