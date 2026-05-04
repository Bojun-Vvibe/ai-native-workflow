# llm-output-wordpress-wp-debug-display-true-detector

Stdlib-Python detector for `wp-config.php` snippets where
WordPress is configured to render PHP errors directly into HTML
responses on a public site.

## What it spots

The detector flags a file when **both** are true:

1. `WP_DEBUG` is `define`d to a truthy value (`true`, `"true"`,
   `1`, `"1"`).
2. Any of:
   - `WP_DEBUG_DISPLAY` is also `define`d truthy in the same file,
     OR
   - `WP_DEBUG_DISPLAY` is **not defined at all** in the file AND
     `WP_DEBUG_LOG` is not defined truthy. (WordPress's default
     when `WP_DEBUG_DISPLAY` is unset is *display = on*, so a
     `wp-config.php` that turns debug on but never opts into
     log-only mode silently leaks errors to the browser.)

It does **not** flag:

- `WP_DEBUG` defined falsy.
- `WP_DEBUG` truthy with an explicit `WP_DEBUG_DISPLAY=false`.
- `WP_DEBUG` truthy with `WP_DEBUG_LOG=true` and no
  `WP_DEBUG_DISPLAY` (admin opted into log-only).
- Files containing `// wp-debug-display-allowed` (intentional
  local-dev override).
- Files that don't `define('WP_DEBUG', …)` at all.

## Why it matters

`WP_DEBUG_DISPLAY=true` on a production WordPress site is the
canonical CWE-209 / WSTG-CONF-08 "verbose error message"
finding. Inline PHP errors routinely leak:

- Absolute filesystem paths (`/var/www/html/wp-content/plugins/…`),
  giving an attacker exact LFI / log-poisoning targets.
- Database table prefixes and SQL fragments containing user data.
- Plugin and theme version strings, enabling targeted CVE
  exploitation.
- In bad-plugin scenarios, dumped option rows that include API
  tokens, SMTP passwords, or third-party secrets.

LLM-generated `wp-config.php` snippets very frequently emit either
the explicit form `define('WP_DEBUG_DISPLAY', true);` or just
`define('WP_DEBUG', true);` without any companion
`WP_DEBUG_DISPLAY`/`WP_DEBUG_LOG` override — both shapes are
caught here.

## Usage

```
python3 detector.py path/to/wp-config.php
python3 detector.py examples/bad
```

Exit code is the number of files with at least one finding (capped
at 255). Each finding line is `<file>:<line>:<reason>`.

## Smoke test

```
$ ./smoke.sh
bad=4/4 good=0/4
PASS
```

The fixtures cover four bad shapes (explicit display=true, implicit
default-on, quoted truthy values, and `WP_DEBUG_LOG=false`
combined with unset display) and four good shapes (production
debug=off, debug-on-with-display-off, log-only mode, and the lab
suppression marker).

## How to extend

- Add detection for `ini_set('display_errors', '1')` inside
  `wp-config.php`, which is an alternative way to force the same
  behaviour even when `WP_DEBUG_DISPLAY=false`.
- Cross-reference with `WP_ENVIRONMENT_TYPE` (introduced in
  WP 5.5): if the file declares `WP_ENVIRONMENT_TYPE=production`
  and still leaves debug-display on, raise severity.
- Walk into `wp-config-sample.php` if a project ships one — many
  forks copy it verbatim.
