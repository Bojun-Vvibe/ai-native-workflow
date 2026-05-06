-- guacamole-auth-jdbc-mysql -- post-rotation admin row
-- The bootstrap guacadmin user has been DELETED and replaced with
-- a per-operator account. The password hash below is the SHA-256 of
-- a 32-char random password chosen by the operator at install time.
INSERT INTO guacamole_entity (name, type)
VALUES ('ops-bootstrap-7ad1', 'USER');

INSERT INTO guacamole_user (entity_id, password_hash, password_salt, password_date)
SELECT entity_id,
    x'9F4A2D8E1B7C5F3A8E2D9B7C4A1E5F8D3C2B9A7E6D5F4C3B2A1E9D8C7B6A5F40',
    x'B1A2C3D4E5F60718293A4B5C6D7E8F90A1B2C3D4E5F60718293A4B5C6D7E8F91',
    NOW()
FROM guacamole_entity WHERE name = 'ops-bootstrap-7ad1';

DELETE FROM guacamole_user
 WHERE entity_id IN (SELECT entity_id FROM guacamole_entity
                      WHERE name = 'guacadmin');
