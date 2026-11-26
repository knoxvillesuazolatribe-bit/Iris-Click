-- =====================================================================================
-- IrisClick v1.0 -- Final database settlement (Supabase SQL Editor)
--
-- APPLIED to the live database on 2026-11-26 (sections 1-5). This file now records the
-- final state and can be re-run safely: every statement is idempotent.
--
-- Final live state (verified after applying):
--   * Schema "irisclick": 21 tables + alembic_version at 0012 = 22 tables. The SQLAlchemy
--     models and the live database match exactly (alembic compare_metadata: 0 differences).
--   * Row-Level Security ON for all 22 tables, with no policies: default-deny for every
--     client role. The server's role "postgres" has BYPASSRLS, so the app is unaffected.
--   * anon / authenticated: no usage on schema irisclick and 0 table grants.
--   * Every foreign key uses ON DELETE CASCADE (rows owned by a user) or SET NULL
--     (who-did-it columns such as created_by / updated_by).
--   * The 9 legacy prototype tables in "public" are DROPPED (section 4). No code referred
--     to them. A snapshot (password hashes redacted) is kept outside git:
--     supabase/archive/old_prototype_tables_backup.sql (gitignored).
--   * Indexes: user_id, log dates and activation ids are indexed. Unindexed created_at /
--     status columns are on tables of at most ~1,100 rows, where an index gives no
--     measurable gain, so none are added (they would also make the database differ from
--     the models).
-- =====================================================================================

-- 1) Pre-check: the server's role must bypass RLS, or section 2 would block the app.
--    Expected: current_user = postgres, rolbypassrls = true. STOP if it is false.
select current_user, r.rolbypassrls
from pg_roles r
where r.rolname = current_user;

-- 2) Row-Level Security on every IrisClick table (default-deny for clients).
begin;
do $$
declare t record;
begin
  for t in select tablename from pg_tables where schemaname = 'irisclick' loop
    execute format('alter table irisclick.%I enable row level security', t.tablename);
  end loop;
end $$;

-- Keep client roles out of the schema entirely.
revoke all on schema irisclick from anon, authenticated, public;
revoke all on all tables in schema irisclick from anon, authenticated, public;
revoke all on all sequences in schema irisclick from anon, authenticated, public;
alter default privileges in schema irisclick revoke all on tables from anon, authenticated, public;
alter default privileges in schema irisclick revoke all on sequences from anon, authenticated, public;
commit;

-- 3) Legacy prototype tables: client grants removed before the drop (no-op once dropped).
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

-- 4) Drop the 9 legacy prototype tables (not used by IrisClick v1.0). Their only foreign
--    keys point at each other, so CASCADE removes nothing outside this list.
--    Applied 2026-11-26 after the snapshot above was proven to restore.
begin;
drop table if exists public."SYSTEM_USER", public.activity_log, public.calibration_profile,
  public.communication_logs, public.screenshot_logs, public.sos_contacts, public.sos_history,
  public.user_settings, public.alembic_version cascade;
commit;

-- 5) Verify. Expected:
--    a) 22 rows, all irisclick, rls = true (no public tables listed);
--    b) no rows.
select schemaname, tablename, rowsecurity as rls
from pg_tables
where schemaname in ('irisclick', 'public')
order by 1, 2;

select table_schema, table_name, grantee, string_agg(privilege_type, ',') as privileges
from information_schema.role_table_grants
where table_schema in ('irisclick', 'public') and grantee in ('anon', 'authenticated')
group by 1, 2, 3;
