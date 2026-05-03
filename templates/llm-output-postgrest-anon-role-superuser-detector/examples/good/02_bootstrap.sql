-- Bootstrap PostgREST schema correctly.
-- The anon role is NOLOGIN, has no inherited privileges, and is
-- granted USAGE on the api schema plus SELECT on exactly the views
-- we mean to expose. JWT-authenticated requests switch to the
-- per-user role via SET ROLE.
\set ON_ERROR_STOP on
-- PGRST_DB_ANON_ROLE=web_anon
CREATE ROLE web_anon NOLOGIN;
GRANT USAGE ON SCHEMA api TO web_anon;
GRANT SELECT ON api.public_articles TO web_anon;
GRANT SELECT ON api.public_authors TO web_anon;
