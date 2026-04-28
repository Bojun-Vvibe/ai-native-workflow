-- BAD: qualified star — t.* still expands every column from t.
SELECT u.*
FROM users u
WHERE u.email = 'someone@example.org';

-- BAD: mixing qualified star with explicit columns
SELECT u.*, o.id AS order_id
FROM users u
JOIN orders o ON o.user_id = u.id;
