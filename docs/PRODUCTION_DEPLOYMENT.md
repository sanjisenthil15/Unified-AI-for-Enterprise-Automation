# Production deployment runbook

For the operator who deploys this release to Render (backend + static frontend)
backed by Supabase Postgres. **Nothing in this file has been executed against
production.**

Every step is tagged:

- **[HUMAN]**: a person with production access must do it.
- **[AUTO]**: happens by itself, or is a scriptable check.
- **[DECISION]**: needs an explicit business / cost approval first.

Never paste real secrets, passwords or connection strings into tickets, chat,
commit messages or this file.

---

## 1. Pre-deployment checklist

| # | Item | Type |
|---|---|---|
| 1 | Supabase backup taken and restorable (section 2) | HUMAN |
| 2 | Production Alembic revision read and equal to `4f6d3fc0cb83` (section 3) | HUMAN |
| 3 | Render env vars reviewed against section 7, especially `SECRET_KEY`, `CORS_ORIGINS`, `AUTH_DISABLED=false` | HUMAN |
| 4 | Decision recorded on public self-registration (`ALLOW_PUBLIC_REGISTRATION`, section 7) | DECISION |
| 5 | Decision recorded on the scheduler mode (section 9) | DECISION |
| 7 | Only intended files committed. Local test reports (`full_backend_run.xml`, `gemini_run.xml`, `test_hardening.xml`, `backend/full_backend_run.xml`) are **not** part of the release | HUMAN |
| 8 | Deployment window announced (Render free plan restarts cause a short outage) | HUMAN |
| 9 | Supabase Storage buckets created and storage env vars set (section 19); otherwise accept that uploads are lost on restarts | HUMAN + DECISION |

## 2. Database backup [HUMAN]

1. Supabase dashboard → Project → Database → Backups: confirm the latest daily
   backup exists (or trigger a manual backup if your plan supports it).
2. Additionally take a logical dump from a trusted machine (connection string
   from the Supabase dashboard, kept in an environment variable, never typed
   into shell history):
   ```bash
   pg_dump --format=custom --no-owner --file=enterprise_pre_release.dump "$PROD_DATABASE_URL"
   pg_restore --list enterprise_pre_release.dump | head   # sanity check the archive
   ```
3. Store the dump somewhere access-controlled. It contains personal data.

## 3. Production migration revision verification [HUMAN, read-only]

Engineering could not verify the production revision. That needs production
credentials, which were intentionally not used. Before deploying, run this
**read-only** query (Supabase SQL editor, or `psql "$PROD_DATABASE_URL"`):

```sql
SELECT version_num FROM alembic_version;
```

- **Expected:** `4f6d3fc0cb83`. That's the newest migration on `main`, and Render's
  start command runs `alembic upgrade head` on every boot.
- **If it differs, stop.** The pending list below would be wrong. Escalate before
  continuing.

## 4. Pending migrations and execution command

Target revision: **`c7d8e9f0a1b2`**. **10 migrations** are pending, applied
strictly in this linear order (20 migrations in total; single root, no
branches, no duplicate IDs):

| Revision | Depends on | What it does | Data impact | Old code OK after it? |
|---|---|---|---|---|
| `a1b2c3d4e5f6` | `4f6d3fc0cb83` | Adds `manager` role | 1 role row | Yes |
| `b2c3d4e5f6a7` | `a1b2c3d4e5f6` | Temporary single-active-manager index | Index only | Yes |
| `f36f281e2838` | `b2c3d4e5f6a7` | Account-security columns on `users` | Defaults; nobody forced to reset | Yes |
| `c1d2e3f4a5b6` | `f36f281e2838` | Action-item review lifecycle, `projects.manager_user_id`, backfills | Existing converted items → `converted` (legacy); others → `proposed` | **No**: old action-item *conversion* violates new CHECK |
| `d2e3f4a5b6c7` | `c1d2e3f4a5b6` | Project lifecycle `status` | Existing projects → `active` | Yes |
| `e3f4a5b6c7d8` | `d2e3f4a5b6c7` | `leave_requests` table | New empty table | Yes |
| `f4a5b6c7d8e9` | `e3f4a5b6c7d8` | Notification categories (backfilled), `escalations`, `scheduled_job_runs` | Backfill of `category` | Yes |
| `a5b6c7d8e9f0` | `f4a5b6c7d8e9` | Append-only `audit_logs` (+ triggers) | New empty table | Yes |
| `b6c7d8e9f0a1` | `a5b6c7d8e9f0` | `auth_attempts`, `support_notification_preferences` | New empty tables | Yes |
| `c7d8e9f0a1b2` | `b6c7d8e9f0a1` | Adds `assigned`, `waiting_for_customer` to the `support_ticket_status` enum | Enum values only; no row changes (runs outside a transaction) | Yes |

**Nothing is destroyed.** No upgrade drops a table or column or deletes rows.

**Locally verified on a disposable database** seeded with production-shaped
legacy data:
- upgrade from `4f6d3fc0cb83` → head;
- downgrade back to `4f6d3fc0cb83` with all legacy rows intact;
- re-upgrade.

**Execution [AUTO by default].** `render.yaml` starts the backend with
`alembic upgrade head && uvicorn …`, so the new backend's first boot migrates
production. If the migration fails, uvicorn never starts and the deploy fails
its health check. Read the deploy log.

**Manual alternative [HUMAN], during the approved window**, from `backend/`
with `DATABASE_URL` set to production in the environment:

```bash
alembic current          # must print 4f6d3fc0cb83
alembic upgrade head     # must end at c7d8e9f0a1b2
alembic current          # confirm c7d8e9f0a1b2 (head)
```

If you migrate manually, deploy the new backend **immediately** afterwards:
`c1d2e3f4a5b6` breaks the old code's action-item conversion.

**Post-migration verification [HUMAN, read-only SQL]:**

```sql
SELECT version_num FROM alembic_version;                                   -- c7d8e9f0a1b2
SELECT review_status, count(*) FROM meeting_action_items GROUP BY 1;        -- only proposed/confirmed/rejected/converted
SELECT status, count(*) FROM projects GROUP BY 1;                           -- existing projects 'active'
SELECT category, count(*) FROM notifications GROUP BY 1;                    -- no NULL category
SELECT count(*) FROM users WHERE must_change_password;                      -- 0 (nobody forced unexpectedly)
SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit_logs'::regclass AND NOT tgisinternal;  -- 2 triggers
```

## 5. Backend deployment

1. **[HUMAN]** Commit only the intended release files, merge to `main` and push.
   Render auto-deploys `enterprise-backend` on push.
2. **[AUTO]** Render runs `pip install -r requirements.txt`, then
   `alembic upgrade head`, then starts uvicorn. The health check is `/health`.
3. **[HUMAN]** Read the deploy log for:
   - `Running upgrade … -> c7d8e9f0a1b2`;
   - `Escalation scheduler started (every 300s)`;
   - no `SECRET_KEY is missing` / `AUTH_DISABLED=true is refused` error (if present, fix the env var and redeploy);
   - a `CRITICAL SECURITY: … demo@demo.com …` line means the published demo password still works. Do section 8 now.

## 6. Frontend deployment

1. **[AUTO]** Render builds `enterprise-frontend` (`npm install && npm run build`)
   from the same push.
2. **[HUMAN]** Confirm `REACT_APP_API_BASE_URL` points at the backend URL *before*
   that build. It's baked in at build time, so changing it later needs a rebuild.
3. **[HUMAN]** Confirm the SPA rewrite works: deep links like `/projects` and
   `/leave` load directly.

## 7. Environment variable checklist [HUMAN]

Names only; never record values here. All names match what the code reads
(`backend/config/settings.py`, `modules/meeting_intelligence/config.py`,
`process.env.*` in the frontend).

| Variable | Service | Required | Used by | What to configure |
|---|---|---|---|---|
| `DATABASE_URL` | backend | **Yes** | SQLAlchemy, Alembic | Supabase connection string (`postgres://` is rewritten to the psycopg driver automatically) |
| `SECRET_KEY` | backend | **Yes** | JWT signing, rate-limit HMAC | Long random value (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). The app **refuses to start** on Render with a placeholder or <16 chars. Changing it logs everyone out |
| `CORS_ORIGINS` | backend | **Yes** | CORS + meeting WebSocket origin check | Exact frontend origin(s), comma-separated. Never `*` |
| `GEMINI_API_KEY` | backend | Yes for AI | Meetings, Intelligence, Support AI | Google AI key. Without it, AI features fall back to rule-based output |
| `AUTH_DISABLED` | backend | Yes (`false`) | Dev bypass | Must be `false`; `true` is refused on Render |
| `DEBUG` | backend | Yes (`false`) | SQL echo | `false` |
| `ALGORITHM` | backend | Optional | JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | backend | Optional | JWT lifetime | `60` |
| `ALLOW_PUBLIC_REGISTRATION` | backend | Optional | `/auth/register` | Leave **unset** = closed on Render (accounts via Admin/HR only). Set `true` only with business approval |
| `TRUST_PROXY_HEADERS` | backend | Optional | Rate-limit client IP | Leave unset (true on Render). Uses the first `X-Forwarded-For` hop; per-account limits never depend on it |
| `LOGIN_RATE_LIMIT_WINDOW_SECONDS`, `LOGIN_MAX_FAILURES_PER_ACCOUNT_IP`, `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_IP`, `REGISTRATION_MAX_PER_IP` | backend | Optional | Rate limiting | Defaults 900 s / 5 / 20 / 50 / 10 per hour |
| `ESCALATION_AUTO_SWEEP`, `ESCALATION_SCHEDULER_ENABLED`, `ESCALATION_SCHEDULER_INTERVAL_SECONDS`, `ESCALATION_SWEEP_INTERVAL_SECONDS`, `LEAVE_PENDING_ESCALATION_HOURS`, `ACTION_ITEM_REVIEW_ESCALATION_HOURS` | backend | Optional | Escalations | Defaults true / true / 300 / 300 / 48 / 72. See section 9 |
| `MEETING_GEMINI_MODEL`, `MEETING_WHISPER_LANGUAGE`, `MEETING_TRANSCRIPTION_PROVIDER` | backend | Set in `render.yaml` | Meeting pipeline | Keep `gemini` transcription on the 512 MB free instance |
| `MEETING_STORAGE_DIR`, `MEETING_MAX_UPLOAD_MB` | backend | Optional | Meeting uploads | Working-copy folder (default `uploads/meetings`) and upload cap (default 1024 MB). **Set `MEETING_MAX_UPLOAD_MB=50` on Supabase's free plan** (section 19) |
| `STORAGE_BACKEND` | backend | **Yes for production** | Permanent file storage | `supabase` (permanent). The default `local` loses files on Render restarts |
| `SUPABASE_URL` | backend | With `supabase` | Storage REST API | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | backend | With `supabase` | Storage REST API (server-side only) | Supabase → Project Settings → API → service_role. **Secret.** Never in the frontend or a `REACT_APP_*` variable. The app refuses to start in `supabase` mode without URL + key |
| `STORAGE_BUCKET_MEETINGS`, `STORAGE_BUCKET_RESUMES` | backend | Optional | Bucket names | Defaults `meeting-recordings`, `recruitment-resumes` |
| `SIGNED_URL_TTL_SECONDS` | backend | Optional | Download links | Default 300 (5 min) |
| `ENVIRONMENT` | backend | Only off-Render | Production safety checks | `production` if hosted anywhere other than Render |
| `PYTHON_VERSION` | backend | Set in `render.yaml` | Render runtime | `3.12.7` |
| `REACT_APP_API_BASE_URL` | frontend | **Yes** | All API calls | Backend public URL, no trailing `/api/v1` |
| `REACT_APP_AUTH_DISABLED` | frontend | Yes (`false`) | Dev bypass | `false` |

The production bundle was scanned: it contains no Gemini key, JWT secret or
database URL. Only the two `REACT_APP_*` values are compiled in.

No Supabase-specific variables (anon / service keys) are used. The app talks to
Supabase only as plain Postgres via `DATABASE_URL`. No email/SMS provider exists;
notifications are in-app only.

## 8. Admin password rotation [HUMAN, right after the backend deploy]

The seed migration created `demo@demo.com`. Its default password was published
in this repository's history, so treat it as compromised until rotated.

**Do it after section 5.** Both methods need columns added by migration
`f36f281e2838`, so they can't run against the old schema.

**Preferred method:** the in-app flow. It's audited, needs no shell, and works on the free plan.

1. Sign in as `demo@demo.com` (the operator who holds the current password).
2. Profile → Change password → enter a new strong password (≥ 8 chars, upper,
   lower, digit; ≤ 72 bytes).
3. **What happens:**
   - all existing sessions for that account are revoked (`token_version` increments);
   - an audit entry `user.password_changed` is recorded.
4. **Verify:**
   - signing in with the old password now fails with 401;
   - the next backend restart no longer logs the CRITICAL demo-password warning.
5. **Optional:** create a named admin account for the real administrator via Employee
   Management, then deactivate `demo@demo.com`.

**Alternative method:** the script, from a trusted machine with `DATABASE_URL` set to
production in the environment.

```bash
cd backend
python -m scripts.rotate_admin_password --email demo@demo.com   # prompts twice, hidden input
```

- **Never use the `--password` option in production.** It puts the password in
  shell history and the process list.
- The script enforces the same password policy and revokes existing sessions.
- It is **not** recorded in the audit log, because it runs outside the web app.

## 9. Scheduler configuration

**Recommendation: A, the in-process scheduler (default; no action, no cost).**

- **How it works:** each backend worker ticks every 300 s. A Postgres row lock
  (`scheduled_job_runs`, `FOR UPDATE SKIP LOCKED`) plus a throttle make exactly
  one sweep run per interval across all workers and instances.
- **Duplicates are impossible:** escalations are unique per (rule, entity), and
  notifications carry dedupe keys.
- **Concurrency is tested**, with 8 parallel workers.
- **Trade-off on the free plan:** the service sleeps after ~15 min idle, so no
  checks run while nobody uses the app. The first tick after waking (~30 s)
  catches up.
- **Why that's acceptable:** the thresholds are 48 h (leave) and 72 h (action
  items), and escalations are only visible when someone opens the app anyway.

**Option B, a Render Cron Job [DECISION: paid].** Adopt only if escalations must
fire while the app is idle.

| Setting | Value |
|---|---|
| Type | Cron Job |
| Root directory | `backend` |
| Build command | `pip install -r requirements.txt` |
| Command | `python -m scripts.run_escalation_sweep` |
| Schedule | `*/15 * * * *` |
| Environment | `DATABASE_URL`, `SECRET_KEY` (same values as the web service), `PYTHON_VERSION` |

- **Cost:** Render bills cron jobs per running minute, with a small monthly
  minimum. There's no free tier.
- **Safe alongside A:** it shares the database lock with the web scheduler.
- **Optional:** set `ESCALATION_SCHEDULER_ENABLED=false` on the web service so
  only the cron job sweeps.
- **Alternative with the same effect:** a paid always-on web instance (no sleep)
  also gives continuous checks.
- **Manual check:** Admin → Notifications → "Run check now" stays available in
  both modes.

## 10. Health-check verification [AUTO + HUMAN]

```bash
curl -fsS https://<backend-host>/health                                # {"status":"ok",...}
curl -fsS https://<backend-host>/api/v1/auth/registration-status       # {"enabled":false} unless approved otherwise
```

`/health` doesn't touch the database. Database health is shown by sign-in
working (section 11).

## 11. Authentication smoke tests [HUMAN]

- Sign in as admin; the dashboard loads.
- A wrong password returns "Invalid email or password". **Rate limit:** the 6th
  wrong attempt for the same account from the same network returns 429 ("Too many
  failed sign-in attempts"). Wait 15 min or use a different test account.
  *Don't* test this on the real admin account.
- `/register` shows "Self-registration is turned off" (unless approved).
- Onboard a test employee via Employee Management, then:
  1. Sign in with the temporary password. You should be forced to change it.
  2. Change it, then sign in with the new password.
  3. Have an admin reset it. The employee's old session is revoked.

## 12. RBAC verification [HUMAN]

With test accounts (employee, manager, HR, viewer):

- Employee: `/audit-log` redirects away; Analytics isn't in the sidebar.
- HR: Leave approval queue visible; Audit Log not.
- Manager: Projects shows only their assigned projects.
- Viewer: Analytics shows Overview / Projects / Operations / Trends; **no**
  Workforce tab. Everything is read-only.
- Admin: Audit Log lists the actions above, with request IDs.

## 13. Customer Support and chat smoke tests [HUMAN]

- An employee creates a support ticket, gets a ticket number, sees it in My
  Tickets, and **it is still there after a backend restart** (it's stored in Postgres).
- A support agent replies or changes status. The employee gets a Support
  notification.
- A second employee can't see the first one's ticket, including via global search.
- Private chat: two teammates exchange messages. An admin can't open that thread.
- Group chat:
  - a project member can read and post in the project group;
  - an employee on another project gets "not a member";
  - after moving an employee to another project, they lose the old group immediately.
- On a fresh production database the support ticket list is **empty** and the
  stats are **zero**. Seeded demo tickets #1001–#1003 must never appear, and
  opening `/customer-support/tickets/1001` must return "not found".

## 14. AI / Gemini verification [HUMAN]

- AI Intelligence (admin): project-risk and executive-summary panels load.
  When Gemini is unavailable or over quota, the rule-based fallback text appears
  instead of an error.
- Upload a short meeting recording. It reaches "completed"; or, if over quota,
  it reaches "failed" with a quota message and can be retried later.
- Customer Support chat answers a knowledge-base question.
- The Gemini free tier has small daily quotas. Watch for `quota / rate limit`
  in backend logs.

## 15. Notification and escalation verification [HUMAN]

- Submit a leave request as an employee. HR / Admin see a Leave notification
  and the bell count increases.
- Approve it. The employee gets an approval notification, and those attendance
  days show "on leave".
- Admin → Notifications → "Run check now" returns a sweep summary.
- **Expect a one-time burst** after the first deploy: legacy unreviewed AI action
  items (older than 72 h) are escalated once per meeting to that project's
  Manager / Team Lead (or Admins).

## 16. Post-deployment monitoring [HUMAN]

For the first days, watch the Render backend logs for:

| Log line | What it means / what to do |
|---|---|
| `Escalation sweep ran: N opened, M resolved` | Normal (every ≤5 min while awake) |
| `Escalation sweep failed` | Investigate the database / connection |
| `Too many failed sign-in attempts` spikes | Possible brute force |
| `Gemini quota / rate limit` | AI is degraded to the fallback |
| `CRITICAL SECURITY` | Demo password still active |

Also:
- Check Supabase disk / connection usage.
- Review the Audit Log for unexpected `auth.login_failed` bursts or admin actions.

## 17. Rollback procedure [HUMAN]

1. **Application rollback (preferred, fast). Read the warning first.**
   - **Warning:** a plain "redeploy previous deploy" **will fail to start**. The
     previous release's start command runs `alembic upgrade head`. Its migration
     folder doesn't know `c7d8e9f0a1b2`, so Alembic exits with
     `Can't locate revision identified by 'c7d8e9f0a1b2'` and uvicorn never starts.
     This was verified locally against a database at the new head.
   - **Procedure:**
     1. Render → `enterprise-backend` → Settings → Start Command → temporarily set
        `uvicorn main:app --host 0.0.0.0 --port $PORT` (no Alembic).
     2. Redeploy the previous successful deploy. Do the same for the frontend.
     3. The old code then runs on the new schema, **except** meeting action-item
        conversion (blocked by `c1d2e3f4a5b6`'s CHECK constraint).
     4. Restore the original start command when rolling forward again.
2. **Schema rollback (only if required).**
   - Command: `alembic downgrade 4f6d3fc0cb83` from the **new** code checkout.
   - It **drops** `auth_attempts`, `support_notification_preferences`, `audit_logs`,
     `escalations`, `scheduled_job_runs` and `leave_requests`. Leave history, audit
     history and escalations are lost, so take a fresh backup first.
   - It aborts if more than one active Manager exists.
3. **Full restore.** Restore the section 2 dump into a fresh Supabase database
   and point `DATABASE_URL` at it. Any data written after the backup is lost.

## 18. Known limitations and operational risks

- **Ticket statuses.** Database, API and UI agree on seven statuses: open,
  assigned, in_progress, waiting_for_customer, resolved, closed, escalated
  (migration `c7d8e9f0a1b2`). Anything else is rejected with HTTP 422.
- **Built-in knowledge base.** The support assistant's built-in knowledge
  articles ship with the code and are counted in `total_knowledge_docs`. That's
  intended content, not sample tickets.
- **File storage depends on configuration.**
  - With `STORAGE_BACKEND=supabase` (section 19), resume PDFs and original
    meeting recordings are permanent.
  - With the default `local`, Render wipes them on every deploy / restart
    (startup logs a warning). Extracted text, transcripts and analyses are in
    Postgres either way.
  - Files uploaded before this release were on Render's disk and are already
    gone. Their rows keep their text and answer "no longer available" for downloads.
- **No project attachments.** This codebase has no project-attachment upload
  feature, so there is nothing to store for it. Adding one would be a new
  feature.
- **Free-plan sleep.** The first request after idle takes ~30–60 s. Scheduler
  gaps are covered in section 9.
- **Online meetings are in-memory and single-instance.** Live meeting rooms don't
  survive restarts and can't be shared across multiple backend instances. Keep one
  instance.
- **Project group-chat override.** Admin, HR Manager and Manager can read any
  project's group chat (not private 1:1 chats). This is existing design; confirm
  it matches your privacy policy. **[DECISION]**
- **Gemini free tier.** Daily quotas run out quickly. AI features then degrade to
  rule-based fallbacks.
- **JWTs in browser localStorage.** These are standard for this SPA design, but
  readable by any XSS. There is no refresh-token rotation; sessions last
  `ACCESS_TOKEN_EXPIRE_MINUTES`.
- **Rate limiting.** The count-then-insert isn't atomic, so a large parallel burst
  can slightly exceed a limit. The IP bucket trusts the first `X-Forwarded-For` hop.

## 19. Persistent file storage (Supabase Storage)

### What is stored where

| Upload | Bucket (private) | Object key | Stored in Postgres |
|---|---|---|---|
| Resume PDF (single + bulk) | `recruitment-resumes` | `job_<jobId>/<uuid>_<safe-name>.pdf` | `resumes.file_path = "obj:recruitment-resumes/<key>"` + extracted text |
| Meeting recording (original upload) | `meeting-recordings` | `<meetingId>/source_<uuid>.<ext>` | `meetings.source_video_path = "<meetingId>/source_…"` (same string as the key) |

- **Meeting processing is unchanged.** FFmpeg, transcription and analysis run on
  a local working copy. After a restart, the original is re-downloaded from the
  bucket on demand.
- **Not stored in the bucket:** extracted audio, which is regenerated when needed,
  so videos are never duplicated.
- **No schema migration is needed.** The existing columns hold the references.

**Access control:**
- Downloads only go through backend endpoints that check permissions first:
  - `GET /api/v1/recruitment/resumes/{id}/download-url`: Admin, HR Manager,
    Recruiter.
  - `GET /api/v1/meetings/{id}/recording/download-url`: same visibility rule as
    the meeting itself.
- They return a signed URL that expires after `SIGNED_URL_TTL_SECONDS`.
- The service-role key never leaves the backend.

### Bucket setup [HUMAN, Supabase dashboard; nothing is created automatically]

1. Storage → New bucket → `recruitment-resumes`:
   - **Public: OFF**;
   - file size limit 10 MB;
   - allowed MIME types `application/pdf`.
2. Storage → New bucket → `meeting-recordings`:
   - **Public: OFF**;
   - file size limit 50 MB (free plan);
   - allowed MIME types `video/*`, `audio/*`.
3. **Policies:** add **no** policies for the `anon` or `authenticated` roles on
   these buckets. The backend uses the service-role key, which bypasses RLS.
   Without policies, browsers can't read, list or upload directly; only signed
   URLs work.
4. In Render (backend), set:
   - `STORAGE_BACKEND=supabase`;
   - `SUPABASE_URL`;
   - `SUPABASE_SERVICE_ROLE_KEY` (secret);
   - `MEETING_MAX_UPLOAD_MB=50`.

   These are changes to Render settings, so **[DECISION]**.

### Limits and cost (verify current numbers on supabase.com/pricing)

- The Free plan includes a small amount of file storage (about 1 GB), a
  per-file upload limit (about 50 MB) and a monthly egress allowance. It's not
  unlimited.
- A handful of meeting videos can fill the quota. Prefer short or compressed
  recordings.
- Delete meetings you don't need: deleting a meeting deletes its stored files.
- Upgrading only means raising the bucket limits and `MEETING_MAX_UPLOAD_MB`.
  No code change.
- Nothing paid is enabled by this release.

### Failure behaviour

- **Storage unreachable on upload:** HTTP 503 "could not be stored", and **no**
  database record is created.
- **Database commit fails after the upload:** the uploaded object is deleted
  again.
- **Leftovers from a crash in between:**
  - Run `python -m scripts.cleanup_orphaned_files` (dry run). Add `--apply` to delete.
  - It only touches files older than 24 h that no row references.
  - It never touches the extracted audio of existing meetings.

### Files uploaded before this release

- They lived on Render's ephemeral disk, so on production they're already gone.
  Their rows keep extracted text and transcripts. Downloads answer "no longer
  available".
- **If you still have copies** (e.g. from a local machine), they can be
  re-attached by hand **[HUMAN]**:
  - **Meetings:** upload `uploads/meetings/<id>/<file>` to bucket
    `meeting-recordings` at key `<id>/<file>`. That key equals the stored path,
    so nothing else changes.
  - **Resumes:** upload to `recruitment-resumes` at `legacy/<file>`, then
    `UPDATE resumes SET file_path = 'obj:recruitment-resumes/legacy/<file>' WHERE id = <id>;`
- Nothing is migrated automatically.

### Verification after enabling Supabase storage [HUMAN]

1. Upload a small resume PDF:
   - it appears in the `recruitment-resumes` bucket;
   - "download URL" works for HR;
   - an employee gets 403.
2. Upload a short meeting video (under 50 MB):
   - it appears in `meeting-recordings`;
   - processing completes;
   - the recording link works for the meeting's owner.
3. Restart the backend (Render → Manual Deploy). Both downloads still work, and
   "Retry processing" on the meeting still finds its video.
4. Open a signed URL after `SIGNED_URL_TTL_SECONDS`. It's refused.
