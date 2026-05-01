# llm-output-ruby-open-uri-ssrf-detector

Static detector for Ruby Server-Side Request Forgery (SSRF) and
file-read footguns introduced when an LLM emits code that passes a
user-controlled string into Ruby's `open-uri` / `Kernel#open` /
`URI.open` / `Net::HTTP.get(URI(...))` without an allow-list.

The CWE-918 (SSRF) classics an LLM produces when it just wants the
fetch to work:

```ruby
require 'open-uri'
body = open(params[:url]).read              # SSRF + file read
body = URI.open(params[:url]).read          # SSRF (Ruby 2.7+)
body = Net::HTTP.get(URI(params[:url]))     # SSRF
```

The first two shapes are doubly bad: pre-Ruby 3.0, `open(string)`
will happily open `"|cat /etc/passwd"` (CWE-78 piped command) or
`"/etc/passwd"` (CWE-22 local file read) in addition to fetching
`http(s)://` URLs.

The safe shape is an explicit `Net::HTTP` call with a parsed URI and
a host allow-list, e.g.:

```ruby
uri = URI.parse(user_input)
raise "bad scheme" unless %w[http https].include?(uri.scheme)
raise "bad host"   unless ALLOWED_HOSTS.include?(uri.host)
Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == 'https') do |http|
  http.get(uri.request_uri).body
end
```

## What this flags

Four related shapes:

1. **ruby-kernel-open-tainted** — bare `open(expr)` / `Kernel.open(expr)`
   where `expr` is not a string literal beginning with a fixed scheme.
2. **ruby-uri-open-tainted** — `URI.open(expr)` / `URI(expr).open` with
   a non-literal argument.
3. **ruby-openuri-require** — file `require 'open-uri'` combined with
   any later `open(...)` call on a non-literal argument (heuristic
   amplifier; reported once per file).
4. **ruby-net-http-get-uri-tainted** — `Net::HTTP.get(URI(expr))`,
   `Net::HTTP.get_response(URI(expr))`, `Net::HTTP.start(expr_host, ...)`
   where the host expression is not a string literal.

A finding is suppressed if the same logical line carries
`# llm-allow:ruby-ssrf`. String literals starting with `"http://"`,
`"https://"`, `'http://'`, `'https://'` are treated as safe (the
detector targets *tainted-input* shapes, not literal fetches).

The detector also extracts fenced ` ```ruby ` / ` ```rb ` code blocks
from Markdown.

## CWE references

* **CWE-918**: Server-Side Request Forgery (SSRF).
* **CWE-22**: Path Traversal (because `Kernel#open` treats `/etc/passwd`
  as a file path).
* **CWE-78**: OS Command Injection (because pre-3.0 `Kernel#open`
  treats `"|cmd"` as a pipe to spawn `cmd`).

## Usage

```
python3 detect.py <file_or_dir> [...]
```

Exit code `1` on any findings, `0` otherwise. python3 stdlib only.

## Worked example

```
$ bash verify.sh
bad findings:  7 (rc=1)
good findings: 0 (rc=0)
PASS
```

See `examples/bad/app.rb` and `examples/good/app.rb` for fixtures.
