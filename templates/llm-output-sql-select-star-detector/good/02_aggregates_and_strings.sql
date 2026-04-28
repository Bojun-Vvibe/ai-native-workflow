-- Aggregate uses of `*` are NOT column-list shortcuts and must NOT trigger.

SELECT COUNT(*) FROM users;

SELECT COUNT(*) AS n_orders
FROM orders
WHERE status = 'open';

SELECT customer_id, COUNT(*) AS n
FROM orders
GROUP BY customer_id
HAVING COUNT(*) > 5;

-- EXISTS subquery — its inner SELECT 1 is fine, and we do not use *.
SELECT u.id, u.email
FROM users u
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.user_id = u.id
);

-- Comments and strings that mention SELECT * must NOT trigger.
-- Example anti-pattern: SELECT * FROM users
/* Another anti-pattern: SELECT t.* FROM things t */
SELECT id FROM things WHERE notes = 'See SELECT * FROM users for context';

-- Arithmetic asterisk is fine.
SELECT id, price * quantity AS total FROM line_items;
