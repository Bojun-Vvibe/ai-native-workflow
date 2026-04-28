-- BAD: DISTINCT * — same problem, plus de-dupe over every column.
SELECT DISTINCT * FROM events WHERE source = 'webhook';

-- BAD: SQL Server style TOP N with star
SELECT TOP 100 * FROM audit_log ORDER BY ts DESC;
