-- guacamole-auth-jdbc-mysql/schema/002-create-admin-user.sql (upstream)
-- Default admin: guacadmin / guacadmin
INSERT INTO guacamole_entity (name, type) VALUES ('guacadmin', 'USER');

INSERT INTO guacamole_user (entity_id, password_hash, password_salt, password_date)
SELECT entity_id,
    x'CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960',
    x'FE24ADC5E11E2B25288D1704ABE67A79E342ECC26064CE69C5B3177795A82264',
    NOW()
FROM guacamole_entity WHERE name = 'guacadmin';
