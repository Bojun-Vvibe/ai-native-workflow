-- BAD: SELECT * inside a subquery / CTE is just as bad — the outer
-- query depends on whatever columns the inner query yields.
WITH recent AS (
    SELECT * FROM events WHERE ts > NOW() - INTERVAL '1 day'
)
SELECT id, payload FROM recent;

-- BAD: INSERT ... SELECT * is the most dangerous form: a schema
-- change to either side silently corrupts inserts.
INSERT INTO archive_events
SELECT * FROM events WHERE archived_at IS NOT NULL;
