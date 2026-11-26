-- =====================================================================================
-- IrisClick v1.0 -- Final database settlement (Supabase SQL Editor)
-- Audited read-only against the live database on 2026-11-26.
--
-- What the audit found (nothing here changes columns or data):
--   * Schema "irisclick": 21 tables + alembic_version at 0012. The SQLAlchemy models and
--     the live database match exactly (alembic compare_metadata: 0 differences).
--   * Every foreign key already uses ON DELETE CASCADE (rows owned by a user) or
--     SET NULL (who-did-it columns such as created_by / updated_by).
--   * anon and authenticated have NO usage on schema irisclick and NO table grants,
--     so the Supabase Data API cannot read or write it. Only the server (role
--     "postgres", which has BYPASSRLS) uses it.
--   * RLS is OFF on all irisclick tables. Section 2 turns it ON with no policies:
--     default-deny for every client role, no effect on the server (BYPASSRLS).
--   * The 9 legacy tables in "public" (old prototype) have RLS ON and no policies, so
--     anon/authenticated already get zero rows -- but they still hold full grants.
--     Section 3 removes those grants. Dropping the tables is optional (section 4).
--   * Indexes: user_id, log dates and activation ids are indexed. Unindexed
--     created_at / status columns are on tables of at most ~1,100 rows, where an
--     index gives no measurable gain, so none are added here (they would also make
--     the database differ from the models).
--
-- Safe to run more than once. Run sections 1-3 and 5. Read section 4 first.
-- =====================================================================================

-- 1) Pre-check: the server's role must bypass RLS, or section 2 would block the app.
--    Expected: current_user = postgres, rolbypassrls = true. STOP if it is false.
select current_user, r.rolbypassrls
from pg_roles r
where r.rolname = current_user;

-- 2) Turn on Row-Level Security on every IrisClick table (default-deny for clients).
begin;
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'irisclick' loop
    execute format('alter table irisclick.%I enable row level security', t.tablename);
  end loop;
end $$;

-- Keep client roles out of the schema entirely (already true today; this makes it explicit).
revoke all on schema irisclick from anon, authenticated, public;
revoke all on all tables in schema irisclick from anon, authenticated, public;
revoke all on all sequences in schema irisclick from anon, authenticated, public;
alter default privileges in schema irisclick revoke all on tables from anon, authenticated, public;
alter default privileges in schema irisclick revoke all on sequences from anon, authenticated, public;
commit;

-- 3) Legacy prototype tables in "public": remove the leftover client grants.
--    RLS is already on with no policies, so this changes nothing the app uses.
begin;
do $$
declare t record;
begin
  for t in select tablename from pg_tables
           where schemaname = 'public'
             and tablename in ('SYSTEM_USER', 'activity_log', 'alembic_version', 'calibration_profile',
                               'communication_logs', 'screenshot_logs', 'sos_contacts', 'sos_history',
                               'user_settings') loop
    execute format('revoke all on table public.%I from anon, authenticated', t.tablename);
  end loop;
end $$;
commit;

-- 4) OPTIONAL -- drop the legacy prototype tables (they are NOT used by IrisClick v1.0;
--    "SYSTEM_USER" still holds two old password hashes). This deletes data permanently.
--    Export them first (Table Editor -> Export to CSV) if anyone may need them.
--    Uncomment only after the team agrees.
-- begin;
-- drop table if exists public."SYSTEM_USER", public.activity_log, public.calibration_profile,
--   public.communication_logs, public.screenshot_logs, public.sos_contacts, public.sos_history,
--   public.user_settings, public.alembic_version cascade;
-- commit;

-- 5) Verify. Expected: every row rls = true; the grants query returns no rows.
select schemaname, tablename, rowsecurity as rls
from pg_tables
where schemaname in ('irisclick', 'public')
order by 1, 2;

select table_schema, table_name, grantee, string_agg(privilege_type, ',') as privileges
from information_schema.role_table_grants
where table_schema in ('irisclick', 'public') and grantee in ('anon', 'authenticated')
group by 1, 2, 3;
