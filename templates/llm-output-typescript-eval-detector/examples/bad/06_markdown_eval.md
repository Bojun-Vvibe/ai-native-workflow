// Markdown doc that pastes an LLM-emitted snippet.

Here's how to evaluate a user expression:

```ts
const expr = req.body.expr;
const v = eval(expr);
console.log(v);
```
