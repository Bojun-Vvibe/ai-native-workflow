#!/usr/bin/env python3
"""llm-output-python-mutable-default-arg-detector.

Pure-stdlib, code-fence-aware detector for Python code blocks emitted
by an LLM that use a *mutable* default argument value in a function or
method definition. The classic footgun::

    def append_item(item, bucket=[]):
        bucket.append(item)
        return bucket

The default `[]` is evaluated **once**, at function-definition time,
and shared across every call that does not supply `bucket` explicitly.
The list grows on each call, surprising every reader who expected a
fresh empty list per invocation.

The same hazard applies to ``{}`` (dict), ``set()``, and any literal
that produces a mutable container.

Why an LLM detector
-------------------
LLMs love to produce Python snippets like

    def memo(x, cache={}):
        if x in cache: return cache[x]
        cache[x] = ... ; return cache[x]

as a "memoization" pattern, which is exactly the bug. The fix is the
universally-recommended sentinel pattern::

    def append_item(item, bucket=None):
        if bucket is None:
            bucket = []
        bucket.append(item)
        return bucket

Detection strategy
------------------
We use the standard library ``ast`` module on each fenced ``python``
/ ``py`` / ``python3`` block. For every ``FunctionDef`` and
``AsyncFunctionDef`` node we walk both ``args.defaults`` and
``args.kw_defaults`` and flag any default whose AST node is one of:

* ``ast.List``        — ``[]`` or ``[1, 2]``
* ``ast.Dict``        — ``{}`` or ``{"k": "v"}``
* ``ast.Set``         — ``{1, 2}``
* ``ast.ListComp`` / ``ast.SetComp`` / ``ast.DictComp``
* ``ast.Call`` whose callable is a bare name in
  ``{"list", "dict", "set", "bytearray", "deque", "defaultdict",
  "OrderedDict", "Counter"}`` — covers ``cache=dict()``,
  ``items=list()``, ``buf=bytearray()`` etc.

Tuples, frozensets, strings, numbers, booleans and ``None`` are
**not** flagged — they are immutable.

Blocks that fail to parse as Python are skipped silently (LLM output
sometimes contains pseudo-code or partial snippets); we do not want
to false-positive on them.

Usage
-----
    python3 detect.py <markdown_file>

Output: one finding per offending parameter on stdout::

    block=<N> start_line=<L> func=<name> param=<p> default=<kind>

Trailing summary ``total_findings=<N> blocks_checked=<M>`` is printed
to stderr. Exit code 0 if no findings, 1 if any.
"""
from __future__ import annotations

import ast
import sys
from typing import List, Tuple


_PY_TAGS = {"python", "py", "python3"}

# Bare-name callables whose return value is a mutable container.
_MUTABLE_FACTORIES = {
    "list",
    "dict",
    "set",
    "bytearray",
    "deque",
    "defaultdict",
    "OrderedDict",
    "Counter",
}


def extract_python_blocks(src: str) -> List[Tuple[int, int, str]]:
    """Return list of (block_idx, start_line_no, body) for python blocks."""
    blocks: List[Tuple[int, int, str]] = []
    lines = src.splitlines()
    i = 0
    in_fence = False
    fence_char = ""
    fence_len = 0
    fence_tag = ""
    body: List[str] = []
    body_start = 0
    block_idx = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if not in_fence:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                ch = stripped[0]
                run = len(stripped) - len(stripped.lstrip(ch))
                if run >= 3:
                    info = stripped[run:].strip()
                    tag = info.split()[0].lower() if info else ""
                    in_fence = True
                    fence_char = ch
                    fence_len = run
                    fence_tag = tag
                    body = []
                    body_start = i + 2
        else:
            if stripped.startswith(fence_char * fence_len) and \
                    set(stripped) <= {fence_char, " ", "\t"}:
                if fence_tag in _PY_TAGS:
                    block_idx += 1
                    blocks.append((block_idx, body_start, "\n".join(body)))
                in_fence = False
                fence_char = ""
                fence_len = 0
                fence_tag = ""
                body = []
            else:
                body.append(line)
        i += 1

    if in_fence and fence_tag in _PY_TAGS:
        block_idx += 1
        blocks.append((block_idx, body_start, "\n".join(body)))

    return blocks


def _classify_default(node: ast.AST) -> str:
    """Return a short tag for a mutable default, or empty string if safe."""
    if isinstance(node, ast.List):
        return "list_literal"
    if isinstance(node, ast.Dict):
        return "dict_literal"
    if isinstance(node, ast.Set):
        return "set_literal"
    if isinstance(node, ast.ListComp):
        return "list_comprehension"
    if isinstance(node, ast.SetComp):
        return "set_comprehension"
    if isinstance(node, ast.DictComp):
        return "dict_comprehension"
    if isinstance(node, ast.Call):
        func = node.func
        # Bare-name call: list(), dict(), defaultdict(int), ...
        if isinstance(func, ast.Name) and func.id in _MUTABLE_FACTORIES:
            return f"call_{func.id}"
        # Attribute-name call we still want to catch: collections.deque()
        if isinstance(func, ast.Attribute) and func.attr in _MUTABLE_FACTORIES:
            return f"call_{func.attr}"
    return ""


def _walk_function_defaults(tree: ast.AST):
    """Yield (func_name, param_name, default_node) for every default."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        # Positional / keyword-or-positional defaults align to the
        # *tail* of args.args + args.posonlyargs.
        positional = list(getattr(args, "posonlyargs", [])) + list(args.args)
        defaults = list(args.defaults)
        if defaults:
            offset = len(positional) - len(defaults)
            for idx, dflt in enumerate(defaults):
                param = positional[offset + idx]
                yield node.name, param.arg, dflt
        # Keyword-only defaults align 1:1 with kwonlyargs.
        for param, dflt in zip(args.kwonlyargs, args.kw_defaults):
            if dflt is None:
                continue  # keyword-only with no default
            yield node.name, param.arg, dflt


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: detect.py <markdown_file>", file=sys.stderr)
        return 2
    with open(argv[1], "r", encoding="utf-8") as fh:
        src = fh.read()

    blocks = extract_python_blocks(src)
    total = 0
    for block_idx, body_start, body in blocks:
        try:
            tree = ast.parse(body)
        except SyntaxError:
            continue
        for func_name, param_name, dflt in _walk_function_defaults(tree):
            kind = _classify_default(dflt)
            if not kind:
                continue
            print(
                f"block={block_idx} start_line={body_start} "
                f"func={func_name} param={param_name} default={kind}"
            )
            total += 1

    print(
        f"total_findings={total} blocks_checked={len(blocks)}",
        file=sys.stderr,
    )
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
