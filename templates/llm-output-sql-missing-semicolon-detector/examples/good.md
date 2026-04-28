# Clean SQL

Every statement is terminated:

```sql
CREATE TABLE users (id INT PRIMARY KEY, name TEXT);
INSERT INTO users VALUES (1, 'alice');
INSERT INTO users VALUES (2, 'bob');
```

Comments and string literals containing `;` should not confuse the
detector:

```sql
-- this is a -- line comment with no semicolon
/* a block comment;
   spanning lines; with stray ; */
SELECT 'a;b;c' AS payload, "weird;col" FROM dual;
INSERT INTO notes VALUES ('he said ''hi;'' loudly');
```

A non-SQL fence next to it should be ignored entirely:

```text
SELECT this is not sql, just prose pretending to be
```
