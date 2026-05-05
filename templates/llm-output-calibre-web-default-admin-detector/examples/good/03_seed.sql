-- bootstrap calibre-web app.db with a rotated admin password hash
-- (argon2id of a freshly generated 24-char password loaded from vault)
INSERT INTO user (id, name, password, role, email)
VALUES (1, 'admin',
        '$argon2id$v=19$m=65536,t=3,p=4$c29tZXNhbHQ$rotated_hash_value',
        7, 'admin@example.com');
