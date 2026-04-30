# llm-output-bind-all-interfaces-detector

Defensive AST-based lint scanner. Catches Python network code that binds a
listener to *every* interface (`0.0.0.0`, `::`, `::0`). LLM-generated server
scaffolds default to `host="0.0.0.0"` because that is the shape every
"hello world Flask app" tutorial uses — which silently exposes dev / admin /
debug endpoints to every network the host touches (corp wifi, container
host, the public internet on a misconfigured VPS).

## What it flags

- `socket.bind(("0.0.0.0", port))` and `socket.bind(("::", port))`
- Stdlib server constructors with a wildcard host tuple:
  `HTTPServer(("0.0.0.0", 8080), Handler)`, `ThreadingHTTPServer(...)`,
  `TCPServer / ThreadingTCPServer / UDPServer / ThreadingUDPServer`
- Framework run/serve calls with `host="0.0.0.0"` keyword:
  Flask `app.run(host="0.0.0.0")`, FastAPI/uvicorn `uvicorn.run(app, host="0.0.0.0")`,
  hypercorn / aiohttp `serve(..., host="0.0.0.0")`,
  Django `runserver("0.0.0.0:8000")`

## What it does not flag

- Loopback binds: `127.0.0.1`, `localhost`, `::1`
- Env-driven hosts: `host=os.environ.get("BIND_HOST", "127.0.0.1")` — that is
  the safe escape hatch this rule wants people to use
- Prose / docstrings / log strings that merely *contain* `0.0.0.0`. The scan
  is AST-based and only fires on real call expressions

## Layout

```
detector.py        # python3 stdlib only, AST based
bad/               # files the detector MUST flag
good/              # files the detector MUST NOT flag
verify.sh          # runs both halves, exits 0 only if both pass
```

## Run it

```
python3 detector.py bad/    # expect findings, non-zero exit
python3 detector.py good/   # expect 0 findings, exit code 0
bash verify.sh              # one-shot: passes only if both halves pass
```

## Verification (worked example)

```
$ bash verify.sh
=== detector vs bad/ (expect findings, non-zero exit) ===
bad/echo_server.py:8:bind(): binds to wildcard host '0.0.0.0'
bad/echo_server.py:19:bind(): binds to wildcard host '::'
bad/web_app.py:13:HTTPServer(): binds to wildcard host '0.0.0.0'
bad/web_app.py:26:run(): host='0.0.0.0' binds to all interfaces
exit=2

=== detector vs good/ (expect 0 findings, exit 0) ===
exit=0

PASS: bad=4 findings (exit 2), good=0 findings (exit 0)
```

## Wiring into CI

Drop `detector.py` into `tools/lint/` and call it from a pre-commit hook
pointed at any directory that contains long-running services or web app
entry points. Non-zero exit fails the gate. Pair with an env-driven host
convention (`BIND_HOST` defaulting to `127.0.0.1`) so operators have a clear,
auditable place to widen exposure when a container actually needs it.
