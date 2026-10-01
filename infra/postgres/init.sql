-- Idempotent M0 database initialization. Runs as the bootstrap superuser (db-init
-- service), never as the runtime role. Safe to re-run on an existing volume.
\set ON_ERROR_STOP on
\set VERBOSITY terse
\getenv app_user APP_DB_USER
\getenv app_password APP_DB_PASSWORD
\getenv db_name PGDATABASE
\getenv mcp_user MCP_DB_USER
\getenv mcp_password MCP_DB_PASSWORD

-- Keep the runtime password out of server error logs.
SET log_min_error_statement = panic;
SET log_statement = 'none';

CREATE EXTENSION IF NOT EXISTS vector;

SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'app_user'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'app_user', :'app_password'
) \gexec

-- M4: read-only login role for fintech-mcp-server. Table grants come from migration 0004.
SELECT format(
    'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'mcp_user'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'mcp_user') \gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    :'mcp_user', :'mcp_password'
) \gexec

REVOKE ALL ON DATABASE :"db_name" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
GRANT CONNECT ON DATABASE :"db_name" TO :"mcp_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"mcp_user";

SELECT 'db-init ok: vector ' || extversion AS result FROM pg_extension WHERE extname = 'vector';
