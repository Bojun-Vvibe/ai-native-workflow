# llm-output-nodejs-mongo-where-detector

A pure-stdlib python3 line scanner that flags Node.js code which
hands the **MongoDB `$where` operator** (or its server-side-eval
cousins) a value that is not a bare literal — i.e. a value built
from request input, a template literal with `${...}`, a `+`
concatenation, or an unbound variable.

`$where` runs an arbitrary JavaScript expression *inside the mongod
process*. If the expression is built from user input, an attacker
gets a JS shell on your database server. The same shape applies to
the deprecated `db.eval(...)` and `Collection.mapReduce(...)` when
they are passed JS-as-a-string built from input.

LLMs reach for `$where` because:

1. The user said "find docs where this complex condition holds" and
   `$where` is the answer the model memorised from a 2014 blog post.
2. The model translated a SQL `WHERE` clause literally.
3. The model wanted regex matching but did not remember `$regex`.

## What this flags

In `*.js`, `*.mjs`, `*.cjs`, `*.ts`, `*.tsx`, `*.jsx` files:

* `{ $where: <non-literal> }` and the quoted-key forms
  `{ "$where": <non-literal> }`, `{ '$where': <non-literal> }`.
* `coll.$where(<non-literal>)` — Mongoose's helper.
* `db.eval(<non-literal>)` — deprecated, still supported on some
  enterprise builds.
* `coll.mapReduce(<non-literal-string>, ...)` — first arg as a
  JS-string built from input. (A function reference like
  `coll.mapReduce(mapFn, ...)` is NOT flagged at this layer.)

A "literal" is one of:

* `'literal'` / `"literal"` — quoted, no `+`, no interpolation
* `` `literal` `` — backtick template with NO `${...}`
* `function (...) { ... }` / `(...) => expr` — function literal with
  no `${...}` and no `+ ` concatenation visible

Anything else is treated as non-literal and is flagged.

## What this does NOT flag

* `{ $where: "this.price > 100" }` — fully literal expression.
* `{ role: role, age: { $gte: minAge } }` — proper Mongo operators.
* `coll.mapReduce(mapFn, reduceFn, opts)` — function references.
* Lines suffixed with the suppression marker `// mongo-where-ok`.
* Mentions inside `/* ... */` block comments.

## CWE references

* **CWE-94**  Improper Control of Generation of Code (Code Injection).
* **CWE-95**  Eval Injection.
* **CWE-943** Improper Neutralization of Special Elements in Data
  Query Logic (NoSQL injection).

## Usage

```
python3 detector.py <file_or_dir> [...]
```

Scans `*.js`, `*.mjs`, `*.cjs`, `*.ts`, `*.tsx`, `*.jsx` under any
directory passed in. Exit `1` if any findings, `0` otherwise.
python3 stdlib only — no Node, no Mongo driver needed.

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
fixtures/bad/03_where_method.js:3: Collection.$where() with non-literal argument: return model.$where(expr).exec();
fixtures/bad/04_db_eval_concat.js:3: db.eval() with non-literal argument: return await db.eval("function() { return " + payload + "; }");
fixtures/bad/02_where_template.mjs:4: $where operator with non-literal value: "$where": `this.role === '${role}'`
fixtures/bad/01_where_concat.js:5: $where operator with non-literal value: $where: "this.price > " + minPrice
fixtures/bad/05_map_reduce_string.ts:3: mapReduce() with non-literal JS string: return await coll.mapReduce("function() { emit(this[" + field + "], 1); }", "function(k,v){return Array.sum(v);}", { out: { inline: 1 } });

$ python3 detector.py fixtures/good/
(no output, exit 0)
```

## Limitations

* Single-line scanner. A multi-line `{ $where:\n  someExpr\n }` will
  be examined line-by-line; if the value spans the next line, the
  detector may miss it.
* The "literal" check rejects template literals that *contain* any
  `${...}` placeholder, even when the placeholder value is itself a
  constant. Inline the constant or refactor to proper operators.
* JSX / TSX text content is treated as code.
* Mongoose's chained `.where("field").equals(val)` is unrelated and
  is not flagged.

## Suppression

After a code review, append the suppression marker to the line:

```js
return model.$where(expr).exec(); // mongo-where-ok
```
