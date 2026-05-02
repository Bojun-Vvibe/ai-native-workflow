-- bootstrap script
SET GLOBAL skip_grant_tables = 1;
FLUSH PRIVILEGES;
CREATE DATABASE IF NOT EXISTS app;
