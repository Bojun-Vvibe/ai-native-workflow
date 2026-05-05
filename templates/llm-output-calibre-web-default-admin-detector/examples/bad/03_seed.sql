-- bootstrap calibre-web app.db with the first admin
INSERT INTO user (id, name, password, role, email)
VALUES (1, 'admin', 'admin123', 7, 'admin@example.com');
