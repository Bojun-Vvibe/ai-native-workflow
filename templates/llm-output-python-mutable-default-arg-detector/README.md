# llm-output-python-mutable-default-arg-detector

A pure-stdlib, code-fence-aware detector for the classic Python
footgun in LLM-emitted snippets: a function or method whose default
argument value is a *mutable* container (list, dict, set, ``list()``,
``dict()``, ``defaultdict(...)``, etc.).

## Why it matters

Default argument values in Python are evaluated **once**, at
function-definition time, and then re-used on every call that does
not explicitly supply that argument. So a snippet like

```python
def append_item(item, bucket=[]):
    bucket.append(item)
    return bucket
```

does *not* give each call its own fresh empty list. The single ``[]``
created when the ``def`` statement ran is shared across every
defaulted call, and grows forever:

```
>>> append_item(1)
[1]
>>> append_item(2)
[1, 2]
>>> append_item(3)
[1, 2, 3]
```

LLMs reproduce this anti-pattern constantly, often as a "memoization"
helper (``cache={}``) which is exactly the bug. The fix is the
universally-recommended sentinel pattern:

```python
def append_item(item, bucket=None):
    if bucket is None:
        bucket = []
    bucket.append(item)
    return bucket
```

This detector is a first-line sniff test that flags the offending
``def`` lines so a reviewer can apply the sentinel pattern.

## How to run

```sh
python3 detect.py path/to/some_markdown.md
```

The script reads the markdown file, finds every fenced code block
whose info-string first token (case-insensitive) is ``python``,
``py``, or ``python3``, parses each one with the standard library
``ast`` module, and walks every ``FunctionDef`` /
``AsyncFunctionDef`` looking at ``args.defaults`` and
``args.kw_defaults``. A default is flagged when the AST node is
one of:

* ``List`` / ``Dict`` / ``Set`` literal
* ``ListComp`` / ``SetComp`` / ``DictComp``
* ``Call`` to a bare or attribute name in
  ``{list, dict, set, bytearray, deque, defaultdict, OrderedDict, Counter}``

Tuples, frozensets, strings, numbers, booleans and ``None`` are
**not** flagged — they are immutable.

Findings go to stdout, summary to stderr, exit code is ``1`` when any
finding is reported and ``0`` otherwise. Each finding line looks
like:

```
block=<N> start_line=<L> func=<name> param=<p> default=<kind>
```

## Expected behavior on the worked examples

```
$ python3 detect.py examples/bad.md
block=1 start_line=9  func=append_item param=bucket  default=list_literal
block=2 start_line=17 func=memo        param=cache   default=dict_literal
block=3 start_line=27 func=collect     param=seen    default=set_literal
block=3 start_line=27 func=collect     param=log     default=call_list
block=3 start_line=27 func=make_index  param=idx     default=call_defaultdict
block=4 start_line=44 func=fetch       param=headers default=dict_literal
total_findings=6 blocks_checked=4
$ echo $?
1

$ python3 detect.py examples/good.md
total_findings=0 blocks_checked=5
$ echo $?
0
```

So ``bad.md`` produces **6 findings** across 4 fenced ``python``
blocks (list literal, dict literal, set literal + ``list()`` factory
+ ``defaultdict(list)`` factory in one block, and a keyword-only dict
default on an ``async def``), and ``good.md`` produces **0 findings**
across 5 ``python``-tagged blocks: the mutable parameters are guarded
with the ``None`` sentinel, the immutable defaults (``"hello"``,
``1``, ``("!",)``, ``frozenset(...)``, ``None``) are accepted as-is,
the bash block is ignored by tag, and the pseudo-code block that
fails to parse is skipped silently. (One ``bash`` block is present
in ``good.md`` and is correctly excluded from the count.)

## What is in scope

* Recognizes both positional defaults (``args.defaults``) and
  keyword-only defaults (``args.kw_defaults``).
* Handles ``async def`` and methods inside classes — anything
  ``ast.walk`` reaches as ``FunctionDef`` / ``AsyncFunctionDef``.
* Handles attribute-form factory calls like ``collections.deque()``
  in addition to bare-name ``deque()``.

## What is out of scope (deliberately)

* Blocks that fail to parse as Python are skipped silently, not
  flagged. LLM output frequently mixes prose and pseudo-code; we
  prefer false negatives to false positives here.
* User-defined factory functions that *return* a mutable container
  (``def make_cache(): return {}``) are not flagged when used as
  ``cache=make_cache()``. Detecting those would require type / data
  flow analysis the AST alone cannot supply.
* We do not try to detect the safe-but-ugly ``bucket=tuple()``
  pattern, since tuples are immutable.

This is a first-line sniff test, not a pylint replacement.
