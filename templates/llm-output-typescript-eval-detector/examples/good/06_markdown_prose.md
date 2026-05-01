// Markdown that documents the anti-pattern but only inside non-code prose.

The function `eval(` should never be called on user input. We ban it
entirely; use a parser. The string `new Function(` is similarly banned.

```text
Bad: eval(req.body.code)
```
