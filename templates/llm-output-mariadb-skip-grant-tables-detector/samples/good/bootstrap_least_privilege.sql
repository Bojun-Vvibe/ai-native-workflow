-- bootstrap.sql — create a least-privilege application user.
-- Password is materialized from the secret store before this file is sourced.
CREATE USER IF NOT EXISTS 'app'@'10.%' IDENTIFIED BY :APP_DB_PASSWORD;
GRANT SELECT, INSERT, UPDATE, DELETE
  ON appdb.*
  TO 'app'@'10.%';
FLUSH PRIVILEGES;
