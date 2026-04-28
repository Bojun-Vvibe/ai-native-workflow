# llm-output-python-asyncio-blocking-call-detector

Flags **synchronous blocking calls** that appear inside `async def`
functions — the classic LLM failure mode of writing async-shaped code
that quietly stalls the event loop.

## What it catches

```python
import time, requests, subprocess

async def fetch_user(uid):
    r = requests.get(f"https://api/{uid}")   # FLAG: sync HTTP
    return r.json()

async def poll():
    while True:
        time.sleep(1)                         # FLAG: use asyncio.sleep
        await do_work()

async def run():
    subprocess.run(["echo", "hi"])            # FLAG: use create_subprocess_exec

async def load(p):
    with open(p) as f:                        # FLAG: blocking file I/O
        return f.read()
```

Recognized blocking APIs:

| API                                                | Reason                                    |
|----------------------------------------------------|-------------------------------------------|
| `time.sleep`                                       | use `await asyncio.sleep(...)`            |
| `requests.{get,post,put,delete,request}`           | use `aiohttp` / `httpx.AsyncClient`       |
| `urllib.request.urlopen`                           | use an async HTTP client                  |
| `subprocess.{run,call,check_output}`               | use `asyncio.create_subprocess_exec`      |
| `socket.{recv,send}`                               | use asyncio streams or `run_in_executor`  |
| `open` (builtin)                                   | use `aiofiles` or `loop.run_in_executor`  |

## What it deliberately ignores

- Calls inside a **nested sync `def`** (or `lambda`) declared within the
  async function — those run off the event loop or are intended for
  `run_in_executor`. The `examples/good/server.py` `_read_file` helper
  is the canonical example.
- `await asyncio.sleep(...)` and other awaited coroutines — never
  flagged.
- Module-level / sync function code — only async paths are scanned.

## Usage

```
python3 detector.py <file.py | file.md> [<file> ...]
```

Markdown ` ```python ` fences are extracted and scanned with original
line numbers preserved.

## Exit codes

| code | meaning              |
|------|----------------------|
| 0    | no findings          |
| 1    | findings reported    |
| 2    | usage / read error   |

## Smoke test

```
$ python3 templates/llm-output-python-asyncio-blocking-call-detector/detector.py \
    templates/llm-output-python-asyncio-blocking-call-detector/examples/bad/server.py
templates/.../examples/bad/server.py:9:  blocking call `requests.get(...)` inside async function — sync HTTP; use `aiohttp` / `httpx.AsyncClient`
templates/.../examples/bad/server.py:16: blocking call `time.sleep(...)` inside async function — blocks event loop; use `await asyncio.sleep(...)`
templates/.../examples/bad/server.py:22: blocking call `subprocess.run(...)` inside async function — blocks; use `asyncio.create_subprocess_exec`
templates/.../examples/bad/server.py:28: blocking call `open(...)` inside async function — sync file I/O; use `aiofiles` or `loop.run_in_executor`
exit=1   # 4 findings

$ python3 .../detector.py .../examples/good/server.py
exit=0   # 0 findings
```

## Implementation notes

- Pure `python3` stdlib (`ast`, `re`). No external deps.
- `_async_depth` / `_sync_def_depth` counters in the AST visitor make
  the "nested sync helper" exemption straightforward.
- Callable resolution is **textual** (dotted path of the call's `func`).
  An aliased import like `from time import sleep as nap` would slip
  past — accepted tradeoff to keep the detector cheap and false-positive
  free on real-world code.
