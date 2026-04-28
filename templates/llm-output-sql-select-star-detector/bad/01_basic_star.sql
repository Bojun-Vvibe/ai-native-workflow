-- BAD: bare SELECT * pulls every column, including potentially large
-- blob columns we do not need.
SELECT * FROM users WHERE id = 42;

-- BAD: SELECT * with a join — guaranteed to break when either table
-- adds a column.
SELECT *
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'open';
