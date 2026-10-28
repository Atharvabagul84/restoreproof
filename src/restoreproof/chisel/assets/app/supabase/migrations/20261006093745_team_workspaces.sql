-- Apply as the Supabase database owner. Authenticated clients have read grants
-- under RLS; all writes go through the narrowly scoped RPCs below. No service
-- role key is needed by the application. Do not expose chisel_private via API.
begin;

-- Private pilot limits, enforced inside the same transaction as each write:
-- 3 owned workspaces/user, 25 briefs/workspace, 20 members including owner,
-- and 25 unexpired, unaccepted, unrevoked invitations/workspace.

create schema if not exists chisel_private;
revoke all on schema chisel_private from public, anon, authenticated;
grant usage on schema chisel_private to authenticated;

create table public.chisel_workspaces (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  name text not null check (pg_catalog.length(pg_catalog.btrim(name)) between 1 and 100),
  created_at timestamptz not null default pg_catalog.now(),
  created_by uuid not null references auth.users(id)
);
create table public.chisel_members (
  workspace_id uuid not null references public.chisel_workspaces(id) on delete cascade,
  user_id uuid not null references auth.users(id),
  email text not null,
  role text not null check (role in ('owner', 'pm', 'engineer')),
  joined_at timestamptz not null default pg_catalog.now(),
  primary key (workspace_id, user_id)
);
create index chisel_members_user_id_idx on public.chisel_members(user_id, workspace_id);
create index chisel_workspaces_creator_idx on public.chisel_workspaces(created_by);
create unique index chisel_members_one_owner_idx on public.chisel_members(workspace_id) where role = 'owner';

create table public.chisel_briefs (
  id uuid primary key,
  workspace_id uuid not null references public.chisel_workspaces(id) on delete cascade,
  draft jsonb not null check (pg_catalog.jsonb_typeof(draft) = 'object' and pg_catalog.octet_length(draft::text) <= 262144),
  revision integer not null check (revision > 0),
  updated_at timestamptz not null default pg_catalog.now(),
  updated_by uuid not null references auth.users(id)
);
create index chisel_briefs_workspace_updated_idx on public.chisel_briefs(workspace_id, updated_at desc);
create table public.chisel_brief_versions (
  brief_id uuid not null references public.chisel_briefs(id) on delete cascade,
  revision integer not null check (revision > 0),
  draft jsonb not null,
  created_at timestamptz not null default pg_catalog.now(),
  created_by uuid not null references auth.users(id),
  primary key (brief_id, revision)
);
create table public.chisel_invitations (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  workspace_id uuid not null references public.chisel_workspaces(id) on delete cascade,
  email text not null,
  role text not null check (role in ('pm', 'engineer')),
  token_hash text not null unique check (token_hash ~ '^[a-f0-9]{64}$'),
  expires_at timestamptz not null default (pg_catalog.now() + interval '7 days'),
  accepted_at timestamptz,
  revoked_at timestamptz,
  created_by uuid not null references auth.users(id)
);
create index chisel_invitations_workspace_idx on public.chisel_invitations(workspace_id);

-- These helpers bypass membership-table RLS to avoid recursive policies. They
-- always identify the caller via auth.uid(), never user-editable JWT metadata.
create function chisel_private.is_member(p_workspace_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.chisel_members m
    where m.workspace_id = p_workspace_id and m.user_id = (select auth.uid()));
$$;
create function chisel_private.is_owner(p_workspace_id uuid) returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (select 1 from public.chisel_members m
    where m.workspace_id = p_workspace_id and m.user_id = (select auth.uid()) and m.role = 'owner');
$$;
create function chisel_private.verified_email() returns text
language plpgsql stable security definer set search_path = '' as $$
declare v_email text;
begin
  select pg_catalog.lower(pg_catalog.btrim(u.email)) into v_email
    from auth.users u where u.id = auth.uid() and u.email_confirmed_at is not null;
  if v_email is null or v_email = '' then
    raise exception 'CHISEL_FORBIDDEN: a verified email is required' using errcode = '42501';
  end if;
  return v_email;
end;
$$;
create function chisel_private.require_member(p_workspace_id uuid, p_owner_only boolean default false) returns uuid
language plpgsql security definer set search_path = '' as $$
declare v_user_id uuid;
begin
  perform chisel_private.verified_email();
  if not chisel_private.is_member(p_workspace_id)
    or (p_owner_only and not chisel_private.is_owner(p_workspace_id)) then
    raise exception 'CHISEL_FORBIDDEN: workspace permission required' using errcode = '42501';
  end if;
  -- Every existing-workspace write locks workspace -> membership -> content.
  -- NO KEY UPDATE serializes capacity checks without conflicting with FK reads.
  perform 1 from public.chisel_workspaces w where w.id = p_workspace_id for no key update;
  -- Hold membership until the write commits, so concurrent removal cannot
  -- succeed while an already-authorized write is still pending.
  select m.user_id into v_user_id from public.chisel_members m
    where m.workspace_id = p_workspace_id and m.user_id = auth.uid()
      and (not p_owner_only or m.role = 'owner') for share;
  if v_user_id is null then
    raise exception 'CHISEL_FORBIDDEN: workspace permission required' using errcode = '42501';
  end if;
  return v_user_id;
end;
$$;

-- Match JavaScript string lengths (UTF-16 code units), including emoji.
create function chisel_private.text_fits(p_value jsonb, p_max integer) returns boolean
language sql immutable set search_path = '' as $$
  select coalesce(pg_catalog.jsonb_typeof(p_value) = 'string' and
    pg_catalog.length(pg_catalog.regexp_replace(p_value #>> '{}', U&'[\+010000-\+10FFFF]', 'xx', 'g')) <= p_max, false);
$$;
create function chisel_private.trim_identifier(p_value text) returns text
language sql immutable set search_path = '' as $$
  select pg_catalog.btrim(p_value, U&'\0009\000A\000B\000C\000D\0020\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000\FEFF');
$$;
create function chisel_private.valid_draft(p_draft jsonb) returns boolean
language plpgsql immutable set search_path = '' as $$
declare
  v_spec jsonb := p_draft -> 'spec';
  v_key text;
  v_entry jsonb;
  v_fields text[];
  v_ids text[];
  v_id text;
  v_date text;
  v_year integer;
  v_month integer;
  v_day integer;
  v_days integer;
begin
  if pg_catalog.jsonb_typeof(p_draft) is distinct from 'object'
    or not chisel_private.text_fits(p_draft -> 'note', 12000)
    or not coalesce(p_draft ->> 'source' in ('example', 'ai', 'manual'), false)
    or not coalesce(p_draft -> 'model' = 'null'::jsonb or chisel_private.text_fits(p_draft -> 'model', 100), false)
    or not (p_draft ? 'generatedAt') or pg_catalog.jsonb_typeof(v_spec) is distinct from 'object' then return false; end if;
  if p_draft -> 'generatedAt' <> 'null'::jsonb then
    if pg_catalog.jsonb_typeof(p_draft -> 'generatedAt') <> 'string' then return false; end if;
    v_date := p_draft ->> 'generatedAt';
    if v_date !~ '^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])T([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]+)?Z$' then return false; end if;
    v_year := pg_catalog.substr(v_date, 1, 4)::integer;
    v_month := pg_catalog.substr(v_date, 6, 2)::integer;
    v_day := pg_catalog.substr(v_date, 9, 2)::integer;
    v_days := (array[31,28,31,30,31,30,31,31,30,31,30,31])[v_month];
    if v_month = 2 and v_year % 4 = 0 and (v_year % 100 <> 0 or v_year % 400 = 0) then v_days := 29; end if;
    if v_day > v_days then return false; end if;
  end if;
  if v_spec - array['title','problem','targetUser','successMetric','inScope','outOfScope','userStories','acceptanceCriteria','assumptions','openQuestions','risks'] <> '{}'::jsonb
    or not chisel_private.text_fits(v_spec -> 'title', 160) then return false; end if;
  foreach v_key in array array['problem','targetUser','successMetric'] loop
    if not chisel_private.text_fits(v_spec -> v_key, 2000) then return false; end if;
  end loop;
  foreach v_key in array array['inScope','outOfScope','assumptions','openQuestions','risks','userStories','acceptanceCriteria'] loop
    if pg_catalog.jsonb_typeof(v_spec -> v_key) is distinct from 'array' then return false; end if;
    if pg_catalog.jsonb_array_length(v_spec -> v_key) > 30 then return false; end if;
    v_ids := array[]::text[];
    for v_entry in select value from pg_catalog.jsonb_array_elements(v_spec -> v_key) loop
      if v_key not in ('userStories', 'acceptanceCriteria') then
        if not chisel_private.text_fits(v_entry, 2000) then return false; end if;
        continue;
      end if;
      if pg_catalog.jsonb_typeof(v_entry) is distinct from 'object'
        or pg_catalog.jsonb_typeof(v_entry -> 'id') is distinct from 'string' then return false; end if;
      v_fields := case when v_key = 'userStories' then array['persona','goal','benefit'] else array['given','when','then'] end;
      if v_entry - (array['id'] || v_fields) <> '{}'::jsonb then return false; end if;
      v_id := chisel_private.trim_identifier(v_entry ->> 'id');
      if v_id !~ '^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$' or v_id = any(v_ids) then return false; end if;
      v_ids := pg_catalog.array_append(v_ids, v_id);
      if not chisel_private.text_fits(v_entry -> v_fields[1], 2000)
        or not chisel_private.text_fits(v_entry -> v_fields[2], 2000)
        or not chisel_private.text_fits(v_entry -> v_fields[3], 2000) then return false; end if;
    end loop;
  end loop;
  return true;
end;
$$;
revoke all on all functions in schema chisel_private from public, anon, authenticated;
grant execute on function chisel_private.is_member(uuid), chisel_private.is_owner(uuid) to authenticated;

alter table public.chisel_workspaces enable row level security;
alter table public.chisel_members enable row level security;
alter table public.chisel_briefs enable row level security;
alter table public.chisel_brief_versions enable row level security;
alter table public.chisel_invitations enable row level security;
create policy chisel_workspace_read on public.chisel_workspaces for select to authenticated
  using (chisel_private.is_member(id));
create policy chisel_member_read on public.chisel_members for select to authenticated
  using (chisel_private.is_member(workspace_id));
create policy chisel_brief_read on public.chisel_briefs for select to authenticated
  using (chisel_private.is_member(workspace_id));
create policy chisel_version_read on public.chisel_brief_versions for select to authenticated
  using (exists (select 1 from public.chisel_briefs b where b.id = brief_id
    and chisel_private.is_member(b.workspace_id)));
create policy chisel_invitation_read on public.chisel_invitations for select to authenticated
  using (chisel_private.is_owner(workspace_id));
-- Explicit revocation also removes any Supabase default grants on new tables.
revoke all on table public.chisel_workspaces, public.chisel_members, public.chisel_briefs,
  public.chisel_brief_versions, public.chisel_invitations from public, anon, authenticated;
grant select on table public.chisel_workspaces, public.chisel_members, public.chisel_briefs,
  public.chisel_brief_versions, public.chisel_invitations to authenticated;

create function public.chisel_create_workspace(p_name text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
  v_email text := chisel_private.verified_email();
  v_user_id uuid := auth.uid();
begin
  if p_name is null or pg_catalog.length(pg_catalog.btrim(p_name)) not between 1 and 100 then
    raise exception 'CHISEL_INVALID_INPUT: workspace name must contain 1 to 100 characters' using errcode = '22023';
  end if;
  perform 1 from auth.users u where u.id = v_user_id for no key update;
  if (select pg_catalog.count(*) from public.chisel_workspaces w where w.created_by = v_user_id) >= 3 then
    raise exception 'CHISEL_LIMIT_REACHED: maximum 3 owned workspaces' using errcode = '22023';
  end if;
  insert into public.chisel_workspaces(name, created_by)
    values (pg_catalog.btrim(p_name), v_user_id) returning id into v_id;
  insert into public.chisel_members(workspace_id, user_id, email, role)
    values (v_id, v_user_id, v_email, 'owner');
  return v_id;
end;
$$;

create function public.chisel_create_invitation(p_workspace_id uuid, p_email text, p_role text, p_token text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_id uuid;
  v_user_id uuid := chisel_private.require_member(p_workspace_id, true);
  v_email text := pg_catalog.lower(pg_catalog.btrim(p_email));
begin
  if v_email is null or pg_catalog.length(v_email) > 254 or v_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
    or p_role is null or p_role not in ('pm', 'engineer')
    or p_token is null or p_token !~ '^[a-f0-9]{64}$' then
    raise exception 'CHISEL_INVALID_INPUT: invitation email, role or token is invalid' using errcode = '22023';
  end if;
  -- Serialize invitation/member changes within a workspace. Accept and remove
  -- use this same lock before changing any invitation or member rows.
  if (select pg_catalog.count(*) from public.chisel_invitations i where i.workspace_id = p_workspace_id
    and i.accepted_at is null and i.revoked_at is null and i.expires_at > pg_catalog.clock_timestamp()) >= 25 then
    raise exception 'CHISEL_LIMIT_REACHED: maximum 25 active invitations per workspace' using errcode = '22023';
  end if;
  insert into public.chisel_invitations(workspace_id, email, role, token_hash, created_by)
    values (p_workspace_id, v_email, p_role,
      pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_token, 'UTF8')), 'hex'), v_user_id)
    returning id into v_id;
  return v_id;
end;
$$;

create function public.chisel_accept_invitation(p_token text) returns uuid
language plpgsql security definer set search_path = '' as $$
declare
  v_email text := chisel_private.verified_email();
  v_hash text;
  v_workspace_id uuid;
  v_invitation public.chisel_invitations;
begin
  if p_token is null or p_token !~ '^[a-f0-9]{64}$' then
    raise exception 'CHISEL_INVALID_INVITATION: invitation is unavailable' using errcode = '22023';
  end if;
  v_hash := pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(p_token, 'UTF8')), 'hex');
  select i.workspace_id into v_workspace_id from public.chisel_invitations i where i.token_hash = v_hash;
  perform 1 from public.chisel_workspaces w where w.id = v_workspace_id for no key update;
  select i.* into v_invitation from public.chisel_invitations i where i.token_hash = v_hash for update;
  if not found or v_invitation.email <> v_email or v_invitation.expires_at <= pg_catalog.clock_timestamp()
    or v_invitation.accepted_at is not null or v_invitation.revoked_at is not null then
    raise exception 'CHISEL_INVALID_INVITATION: invitation is unavailable for this email' using errcode = '22023';
  end if;
  if not exists (select 1 from public.chisel_members m where m.workspace_id = v_workspace_id and m.user_id = auth.uid())
    and (select pg_catalog.count(*) from public.chisel_members m where m.workspace_id = v_workspace_id) >= 20 then
    raise exception 'CHISEL_LIMIT_REACHED: maximum 20 members per workspace' using errcode = '22023';
  end if;
  insert into public.chisel_members(workspace_id, user_id, email, role)
    values (v_invitation.workspace_id, auth.uid(), v_email, v_invitation.role)
    on conflict (workspace_id, user_id) do nothing;
  update public.chisel_invitations set accepted_at = pg_catalog.clock_timestamp() where id = v_invitation.id;
  return v_invitation.workspace_id;
end;
$$;

create function public.chisel_revoke_invitation(p_invitation_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare v_workspace_id uuid;
begin
  select i.workspace_id into v_workspace_id from public.chisel_invitations i where i.id = p_invitation_id;
  perform chisel_private.require_member(v_workspace_id, true);
  update public.chisel_invitations set revoked_at = pg_catalog.clock_timestamp()
    where id = p_invitation_id and accepted_at is null and revoked_at is null;
end;
$$;

create function public.chisel_remove_member(p_workspace_id uuid, p_user_id uuid) returns void
language plpgsql security definer set search_path = '' as $$
declare v_email text;
begin
  perform chisel_private.require_member(p_workspace_id, true);
  if exists (select 1 from public.chisel_members m
    where m.workspace_id = p_workspace_id and m.user_id = p_user_id and m.role = 'owner') then
    raise exception 'CHISEL_FORBIDDEN: the workspace owner cannot be removed' using errcode = '42501';
  end if;
  delete from public.chisel_members m where m.workspace_id = p_workspace_id and m.user_id = p_user_id
    returning m.email into v_email;
  -- Removal must not leave a pre-existing invitation usable to rejoin.
  update public.chisel_invitations set revoked_at = pg_catalog.clock_timestamp()
    where workspace_id = p_workspace_id and email = v_email and accepted_at is null and revoked_at is null;
end;
$$;

create function public.chisel_save_brief(p_workspace_id uuid, p_brief_id uuid, p_expected_revision integer, p_draft jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  v_user_id uuid := chisel_private.require_member(p_workspace_id);
  v_brief public.chisel_briefs;
  v_exists boolean;
  v_revision integer;
  v_updated_at timestamptz := pg_catalog.date_trunc('milliseconds', pg_catalog.clock_timestamp());
  v_draft jsonb;
begin
  if p_brief_id is null or p_expected_revision is null or p_expected_revision < 0
    or p_expected_revision = 2147483647 or p_draft is null
    or not chisel_private.valid_draft(p_draft) or pg_catalog.octet_length(p_draft::text) > 262144 then
    raise exception 'CHISEL_INVALID_INPUT: draft, id or revision is invalid' using errcode = '22023';
  end if;
  select b.* into v_brief from public.chisel_briefs b where b.id = p_brief_id for update;
  v_exists := found;
  if v_exists and v_brief.workspace_id <> p_workspace_id then
    raise exception 'CHISEL_FORBIDDEN: brief belongs to another workspace' using errcode = '42501';
  end if;
  if (v_exists and v_brief.revision <> p_expected_revision) or (not v_exists and p_expected_revision <> 0) then
    raise exception 'CHISEL_REVISION_CONFLICT: reopen the latest saved revision' using errcode = '40001';
  end if;
  if not v_exists and (select pg_catalog.count(*) from public.chisel_briefs b where b.workspace_id = p_workspace_id) >= 25 then
    raise exception 'CHISEL_LIMIT_REACHED: maximum 25 briefs per workspace' using errcode = '22023';
  end if;
  v_revision := p_expected_revision + 1;
  v_draft := p_draft || pg_catalog.jsonb_build_object('id', p_brief_id, 'revision', v_revision,
    'updatedAt', pg_catalog.to_char(v_updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"'),
    'checkedIds', '[]'::jsonb);
  if pg_catalog.octet_length(v_draft::text) > 262144 then
    raise exception 'CHISEL_INVALID_INPUT: canonical draft exceeds 256 KiB' using errcode = '22023';
  end if;
  if v_exists then
    update public.chisel_briefs set draft = v_draft, revision = v_revision,
      updated_at = v_updated_at, updated_by = v_user_id where id = p_brief_id returning * into v_brief;
  else
    insert into public.chisel_briefs(id, workspace_id, draft, revision, updated_at, updated_by)
      values (p_brief_id, p_workspace_id, v_draft, v_revision, v_updated_at, v_user_id)
      on conflict (id) do nothing returning * into v_brief;
    if not found then
      raise exception 'CHISEL_REVISION_CONFLICT: another save created this brief' using errcode = '40001';
    end if;
  end if;
  insert into public.chisel_brief_versions(brief_id, revision, draft, created_at, created_by)
    values (p_brief_id, v_revision, v_draft, v_updated_at, v_user_id);
  return pg_catalog.to_jsonb(v_brief);
end;
$$;

revoke all on function public.chisel_create_workspace(text),
  public.chisel_create_invitation(uuid, text, text, text), public.chisel_accept_invitation(text),
  public.chisel_revoke_invitation(uuid), public.chisel_remove_member(uuid, uuid),
  public.chisel_save_brief(uuid, uuid, integer, jsonb) from public, anon, authenticated;
grant execute on function public.chisel_create_workspace(text),
  public.chisel_create_invitation(uuid, text, text, text), public.chisel_accept_invitation(text),
  public.chisel_revoke_invitation(uuid), public.chisel_remove_member(uuid, uuid),
  public.chisel_save_brief(uuid, uuid, integer, jsonb) to authenticated;

commit;
