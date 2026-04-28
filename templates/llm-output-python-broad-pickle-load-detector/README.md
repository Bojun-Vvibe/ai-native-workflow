# llm-output-python-broad-pickle-load-detector

Flags use of `pickle.load`, `pickle.loads`, `pickle.Unpickler`, and the
`cPickle` equivalents in Python source.

## The smell

```python
import pickle

def restore(blob):
    return pickle.loads(blob)   # arbitrary code execution if blob is hostile
```

`pickle` is **not** a data format — it's a tiny VM that runs whatever
opcodes the byte stream contains, including `REDUCE` opcodes that call
arbitrary callables with arbitrary arguments. Loading an attacker-controlled
pickle is equivalent to running their `eval`. The Python docs say so in
bold: *"Never unpickle data received from an untrusted or unauthenticated
source."*

## Why LLMs produce it

`pickle.dump` / `pickle.load` is the most-cited "save and restore an
object" snippet in tutorials. When an LLM is asked "how do I cache this
dict to disk and reload it?", it reaches for pickle by reflex. It
rarely surfaces the security caveat unless explicitly prompted, and
even then it tends to add a `# trusted source only` comment rather
than switching to a safe format.

Safer alternatives, depending on payload shape:

- `json` for plain data;
- `tomllib` (read-only) or `tomli`/`tomli_w` for config;
- `marshal` is no safer — also an LLM trap;
- `dill`, `cloudpickle` — same risk as pickle;
- For binary structured data: `struct`, `msgpack` (data-only mode), or
  a real schema (protobuf, capnp).

## How the detector works

Single-pass scanner over `.py` files:

1. **Mask comments and string literals** including triple-quoted
   strings that span multiple physical lines, so docstrings and
   warning text mentioning `pickle.load` do not trigger.
2. **Parse imports** to learn which local names are bound to
   `pickle` / `cPickle` (including `import pickle as p`) and which
   local names are bound to `load` / `loads` / `Unpickler` from a
   `from pickle import …` form (including `as` aliases).
3. **Match call sites** for `<modname>.(load|loads|Unpickler)(` and
   bare-name calls of imported `load(` / `loads(`.

Stdlib only.

## False-positive caveats

- A user-defined helper function named `loads` that is not imported
  from pickle will not trigger (the detector requires the name to be
  bound to a pickle import).
- A class with a `.load()` method on an arbitrary instance whose
  receiver name happens to match a pickle alias (e.g. `pickle = MyThing()`
  in the same file) will trigger a false positive. Don't shadow the
  pickle name.
- Dynamic imports (`importlib.import_module("pickle")`) are not tracked.
- The detector does **not** distinguish between trusted-source loads
  (e.g. unpickling your own freshly-written cache) and untrusted-source
  loads. It flags both, on purpose. Suppress at the call site if the
  source really is trusted (and document why).

## Usage

```
python3 detector.py path/to/python/project
```

Exit code `0` if no hits, `1` if any.

## Smoke test

See `SMOKE.md`.
