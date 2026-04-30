# llm-output-php-mysqli-query-string-concat-detector

A pure-stdlib python3 line scanner that flags PHP code which passes
a **non-literal SQL string** into the mysqli query sinks:

* `mysqli_query($link, $sql)` (procedural)
* `mysqli_real_query($link, $sql)` (procedural)
* `mysqli_multi_query($link, $sql)` (procedural)
* `$db->query($sql)` (object-oriented)
* `$db->real_query($sql)` (object-oriented)
* `$db->multi_query($sql)` (object-oriented)

A "non-literal" SQL argument is anything other than a bare quoted
string with no interpolation and no concatenation. Specifically
this detector flags the SQL argument when it contains:

* string concatenation with `.` and a variable, or
* a double-quoted string with `$var` / `{$expr}` interpolation, or
* a heredoc with `$` substitutions, or
* a bare `$variable` reference (worth a manual review).

This is the canonical SQL-injection sink for the procedural and
object-oriented mysqli APIs. The fix is always **prepared
statements** with `mysqli_prepare` / `->prepare` and bound
parameters via `mysqli_stmt_bind_param` / `->bind_param`.

## Why LLMs emit this

1. They were translating "select * where id = X" and the shortest
   path to working PHP is `"SELECT * FROM t WHERE id=$id"`.
2. They saw a 2009 tutorial that used `mysql_query` (not even
   `mysqli`) and forward-ported only the function name.
3. They tried to "sanitise" with `mysqli_real_escape_string` and
   then concatenated, missing that prepared statements are simpler
   and exhaustive.

## CWE / OWASP references

* **CWE-89** Improper Neutralization of Special Elements used in
  an SQL Command (SQL Injection).
* **OWASP A03:2021** Injection.

## What this does NOT flag

* `mysqli_query($conn, "SELECT 1")` — fully literal.
* `mysqli_query($conn, "SELECT id, name FROM users")` —
  double-quoted but no `$` interpolation.
* `mysqli_query($conn, Q_ALL_USERS)` — a bare constant
  identifier (treated as safe; the constant is assumed to be
  defined elsewhere as a literal).
* Calls inside `/* ... */` block comments or after `//` / `#`
  line-comment markers.
* Lines suffixed with the suppression marker `// mysqli-concat-ok`
  (or `# mysqli-concat-ok`).

## Usage

```
python3 detector.py <file_or_dir> [...]
```

Scans `*.php`, `*.phtml`, `*.inc` under any directory passed in.
Exit `1` if any findings, `0` otherwise. python3 stdlib only — no
PHP runtime required.

## Verified worked example

```
$ bash test.sh
bad findings: 5 (expected 5)
good findings: 0 (expected 0)
PASS
```

Real run output over the fixtures:

```
$ python3 detector.py fixtures/bad/
fixtures/bad/02_dq_interp.php:4: mysqli_query() with non-literal SQL: $res = mysqli_query($conn, "SELECT * FROM users WHERE name = '$name'");
fixtures/bad/01_concat.php:4: mysqli_query() with non-literal SQL: $res = mysqli_query($conn, "SELECT * FROM users WHERE id = " . $id);
fixtures/bad/03_oo_query.php:5: mysqli->query() with non-literal SQL: return $db->query("SELECT id FROM users WHERE email = '{$email}'");
fixtures/bad/05_real_query.php:4: mysqli_real_query() with non-literal SQL: mysqli_real_query($conn, $sql);
fixtures/bad/04_multi_query.php:4: mysqli->multi_query() with non-literal SQL: $db->multi_query("SELECT * FROM users WHERE role='" . $role . "'; SELECT 1;");

$ python3 detector.py fixtures/good/
(no output, exit 0)
```

## Limitations

* Single-line scanner. A `mysqli_query(\n  $conn,\n  "..." . $x\n)`
  call split across lines will be examined per-line and may be
  missed if the SQL argument lives on a different line than the
  call name.
* The detector cannot follow data flow: a call like
  `mysqli_query($conn, $sql)` where `$sql` was assigned a literal
  earlier will be flagged as a precaution. Either inline the
  literal or add the suppression marker after review.
* PDO / `mysqli::execute_query` / Doctrine / Eloquent are not
  covered here — they are different sinks and have their own
  detectors.

## Suppression

After a code review, append the suppression marker to the line:

```php
$res = mysqli_query($conn, "TRUNCATE TABLE " . $tbl); // mysqli-concat-ok
```
