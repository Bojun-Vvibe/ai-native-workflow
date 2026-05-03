-- Bootstrap PostgREST schema (don't do this).
-- This file also exports the env var that PostgREST will consume,
-- so the anon role wired here is the one HTTP callers run as.
\set ON_ERROR_STOP on
-- PGRST_DB_ANON_ROLE=web_anon
CREATE ROLE web_anon NOLOGIN;
ALTER ROLE web_anon SUPERUSER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO web_anon;
