# Connect Chisel to Supabase

Use this guide to activate email sign-in, persistent workspaces, shared feature briefs, and invitations for your PM and engineering team.

The connected development pilot has verified email delivery, owner sign-in, workspace creation, and shared-brief persistence after reload. The live two-account collaboration test remains incomplete. See [project status](../reference/status.md) for the verification boundary; the steps below reproduce the setup without exposing that pilot's account configuration or data.

Prepared 6 October 2026. These steps target a new, empty Supabase project. Keep an existing production project separate until its schema and migration history have been reviewed.

## What you need

- A Supabase account and a new project you control.
- An SMTP provider and an authorized sender address for authentication emails.
- Two email accounts you can access for the owner and engineer smoke test.
- The Chisel source folder, Node.js, and npm.

**Email setup is a prerequisite for this build.** Since 3 June 2026, new Free plan projects using Supabase’s default email service cannot change authentication templates. Chisel uses a code email template, so configure custom SMTP first. Paid plans are exempt from the template restriction, but still need appropriate email delivery for a real pilot. [Supabase template change](https://supabase.com/changelog/46599-changes-to-email-template-customisation-on-free-tier).

## 1 Create the project

Open the [Supabase dashboard](https://supabase.com/dashboard), select your organization, and choose New project. Use a recognizable name such as `chisel-pilot`. Choose the region that fits your team and data requirements. Review the plan shown in your dashboard before confirming creation.

Generate a strong database password and store it in your password manager. Chisel does not need that password in its application environment. Wait until the project is ready, then make sure you are viewing this new project before proceeding.

Keep access to the mailbox that will own the Chisel workspace and to the Supabase account’s recovery details. This MVP has one workspace owner and does not yet offer ownership transfer or a second workspace owner. A Supabase organization administrator and a Chisel workspace member are different roles.

## 2 Apply the workspace schema

For a separate new project, open SQL Editor and apply both files from `supabase/migrations/` once, in filename order:

1. `20261006093745_team_workspaces.sql` creates the workspace schema.
2. `20261006094315_private_rpc_implementations.sql` moves privileged functions into the private schema, retains public invoker wrappers, and adds foreign-key indexes.

When resuming an already configured project, check its migration history before applying anything. Both files were applied to the development pilot; they must not be blindly reapplied to a populated project.

The migration creates workspace membership, shared briefs, immutable saved versions, invitation records, access policies, and the database functions used by Chisel. Do not disable row level security to resolve a setup error. Writes go through the supplied functions; the application does not need unrestricted table writes.

After success, run this read-only check in SQL Editor:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename like 'chisel_%'
order by tablename;
```

Expect five rows and `rowsecurity = true`: `chisel_workspaces`, `chisel_members`, `chisel_briefs`, `chisel_brief_versions`, and `chisel_invitations`. The `public` schema must remain available through the Data API. The migration supplies explicit grants together with access policies. [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api).

If SQL reports an error, stop and save that message. Do not rerun arbitrary fragments or delete tables. If you later adopt the Supabase CLI, reconcile this manual application with migration history before using `db push`.

## 3 Configure email delivery and codes

In Authentication, configure custom SMTP using your provider's host, port, username, password, and authorized sender address. Store SMTP credentials in Supabase's configuration; they do not belong in Chisel's source or chat. Complete any sender or domain verification required by that provider. [SMTP setup](https://supabase.com/docs/guides/auth/auth-smtp).

Supabase’s default service sends only to addresses authorized on the Supabase project’s organization team and is currently limited to two messages per hour, with limits subject to change. Inviting someone to a Chisel workspace does not authorize their address for that default service. Custom SMTP is the intended path for the team pilot. [Default email restrictions](https://supabase.com/docs/guides/auth/auth-smtp).

In Authentication → Sign In / Providers, enable email sign-in and allow new users to sign up. Keep email confirmations enabled. Do not enable anonymous sign-in for this workflow. In URL Configuration, set the Site URL to `http://127.0.0.1:3100` while testing locally.

In Authentication → Email Templates, put the following body in both **Magic Link** and **Confirm signup**. Use `Your Chisel sign-in code` as the subject:

```html
<h2>Your Chisel sign-in code</h2>
<p>Enter this code in the Chisel sign-in screen:</p>
<p><strong>{{ .Token }}</strong></p>
<p>If you did not request this code, ignore this email.</p>
```

The `{{ .Token }}` variable supplies the code; a template containing only a confirmation link will not match this build’s sign-in screen. Both templates cover new and returning users. Chisel accepts 6–10 numeric digits and verifies them with Supabase; use the code length configured in your project. This flow does not require an `/auth/callback` route. [Email templates](https://supabase.com/docs/guides/auth/auth-email-templates), [email OTP flow](https://supabase.com/docs/guides/auth/auth-email-passwordless).

Keep OTP expiration and resend limits appropriate for a pilot. Supabase’s documented defaults are a one-hour expiry and 60 seconds between requests; project settings and SMTP limits still apply. Do not repeatedly request codes while debugging delivery. [OTP configuration](https://supabase.com/docs/guides/auth/auth-email-passwordless).

## 4 Connect the local application

From your project’s Connect dialog or API settings, copy the **Project URL** and **publishable key** beginning with `sb_publishable_`. This build expects the new publishable key format. Do not use a secret key, service-role key, database password, or a Supabase personal access token. [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys).

Create or update `.env.local` inside the `Chisel` source folder, alongside `package.json`. Preserve any existing settings you need. Use the values from your own project:

```dotenv
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_YOUR_KEY
CHISEL_APP_URL=http://127.0.0.1:3100
```

Do not add `/auth/v1`, `/rest/v1`, or a page path to the Project URL. `CHISEL_APP_URL` is the exact browser origin allowed to make authenticated changes. For the commands below, open `127.0.0.1`, not `localhost`; their origins differ. Keep `.env.local` out of Git.

In a terminal opened inside the `Chisel` folder, run:

```powershell
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3100
```

Open the Chisel team workspace at `http://127.0.0.1:3100/team`. Restart the server after changing environment variables. The `NEXT_PUBLIC_` variables must also be set before a production build because Next.js embeds those values at build time. [Next.js environment variables](https://nextjs.org/docs/app/guides/environment-variables).

Existing project configuration is external to the repository. Retrieve the values through your authorized Supabase account when setting up another machine; do not publish a populated `.env.local`.

## 5 Verify the complete team workflow

Run this check on the same computer using two separate browser profiles. A local invitation beginning with `127.0.0.1` will not reach your app from a teammate’s computer; remote team testing needs a hosted app address.

1. **Owner:** open `/team`, request a sign-in code, enter it, and create a workspace. Reload the page and confirm the workspace remains.
2. **First brief:** choose New brief, enter the context, edit the scope, and Save in workspace. Reload and reopen it. Check that the original notes and edited fields persist.
3. **Invitation:** under Team members, enter the second account’s exact email and choose Engineer. Create and copy the invitation link. Chisel does not send an invitation email; share the link yourself.
4. **Engineer:** in the second profile, open that link, sign in with the invited address, and explicitly Accept invitation. Confirm that the shared brief appears and an edit saves as a newer revision. A PM invitation can be tested the same way.
5. **Concurrent edits:** open the same saved revision in both profiles. Save a change in one, then try to save a different change in the other. The second save must report a conflict and retain its edits. Download a JSON backup, then Load latest revision before combining changes.
6. **Access controls:** use a third, uninvited account or a signed-out window. It must not list the private workspace. A different email must not accept the invitation. As owner, revoke an unused invitation and verify acceptance fails; remove the engineer and verify new reads and saves are denied. Already downloaded copies cannot be recalled.
7. **Session and recovery:** sign out and confirm `/team` returns to sign-in. Sign in again, reopen the brief, and export a backup. Keep access to your owner mailbox.

Checklist marks are personal aids; saves clear them. They do not record team approval or successful engineering tests. Browser drafts are only uploaded when you explicitly copy one into a workspace and save it. Saved version history exists in the database; an approval and comparison interface is a later milestone.

Current pilot limits are three owned workspaces per user, 25 briefs per workspace, 20 members per workspace, and 25 active pending invitations per workspace. Invitations last seven days and are bound to one verified email address.

## 6 Troubleshoot setup

| What you see | What to check |
| --- | --- |
| Team setup screen still appears | Check both Supabase environment values, the `sb_publishable_` prefix, and restart the app. |
| Templates cannot be edited | Connect custom SMTP on a new Free project. |
| Code email never arrives | Check SMTP credentials, sender verification, spam folder, Supabase Auth logs, and rate limits. |
| Email contains a link but no code | Update both Magic Link and Confirm signup templates with `{{ .Token }}`. |
| Request origin error | Open the exact origin in `CHISEL_APP_URL`, including protocol and port. |
| Workspace or function unavailable | Confirm the full migration succeeded in the same project as the app’s URL and key; keep the Data API and `public` schema available. |
| Invitation rejected | Check invited email, expiry, revocation, and whether it was already used. Generate a fresh link if needed. |
| Save conflict | Keep your edits, export JSON, load the latest revision, then combine changes. |

## 7 Move toward a hosted pilot

For deployment, set the Supabase variables in the hosting environment before building. Set `CHISEL_APP_URL` and Supabase’s Site URL to your final HTTPS origin. Keep preview and production configuration deliberate; do not allow arbitrary origins. Deploy the prepared app and repeat the two-account smoke test at that address before inviting pilot teams.

During development, hosted Auth health and settings passed read-only checks, anonymous workspace reads were denied, and a security-advisor check returned no findings. All five tables have row level security, authenticated direct writes are denied, and only authenticated users can execute the public write wrappers. A performance check on the then-new database reported unused indexes; these historical results do not describe current traffic or replace checks on your project. Retain indexes needed for workspace lookups and foreign-key checks, and evaluate actual usage before changing them. [Supabase unused-index guidance](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).

The recorded implementation checks passed 73 automated tests, including 17 PostgreSQL tests in PGlite. Those tests do not replace real sign-in, email delivery, and authenticated shared-write checks. The connected pilot verified delivery, completed owner sign-in, workspace persistence, and preservation of all 25 editor text fields after saving and reopening a manual brief. Engineer invitation creation, wrong-email rejection, and second-account code delivery were also exercised. Completed engineer sign-in, invitation acceptance, collaboration, and live concurrent edits remain unverified. No deployment of this updated MVP has been verified. See [project status](../reference/status.md) for the next steps.

Production AI generation remains disabled until authenticated usage limits and spend controls are added. Team manual writing, shared saving, and explicit import of existing local drafts are the workflow for this milestone. The next product milestone is revision comparison and PM–engineering review, followed by a controlled pilot.
