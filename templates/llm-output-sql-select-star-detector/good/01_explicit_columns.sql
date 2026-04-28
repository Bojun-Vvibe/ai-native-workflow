-- All queries use explicit column lists. None of these should trigger.

SELECT id, email, created_at
FROM users
WHERE id = 42;

SELECT o.id, o.total_cents, c.email
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = 'open';

SELECT DISTINCT source
FROM events
WHERE ts > NOW() - INTERVAL '1 day';

-- Multi-line column list, still no star.
SELECT
    id,
    email,
    created_at,
    last_login_at
FROM users
ORDER BY created_at DESC
LIMIT 100;
