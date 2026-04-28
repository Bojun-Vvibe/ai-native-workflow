# Some SQL the model wrote

Set up the table and seed it:

```sql
CREATE TABLE users (id INT PRIMARY KEY, name TEXT);
INSERT INTO users VALUES (1, 'alice')
INSERT INTO users VALUES (2, 'bob');
```

A read-only example with another miss:

```sql
SELECT id, name FROM users WHERE id = 1
SELECT count(*) FROM users;
```

A trailing statement with no terminator at all:

```postgresql
UPDATE users SET name = 'carol' WHERE id = 2
```
