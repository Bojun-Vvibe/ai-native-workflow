# Math notes (well-formed)

Inline math like $E = mc^2$ should render fine.

A second paragraph with two inline pieces: $a + b$ and $c - d$ on the same
line, all balanced.

Display math:

$$
\int_{0}^{\infty} e^{-x^2} \, dx = \frac{\sqrt{\pi}}{2}
$$

LaTeX-style brackets also balance:

\(x^2 + y^2 = z^2\) and a display version \[ \sum_{i=1}^{n} i = \frac{n(n+1)}{2} \].

A literal dollar sign is escaped: \$5 should not count.

Inline code with stray dollars is ignored: `price = $5 + $3`.

```
fenced block with $$ unbalanced $ stuff that should be ignored
```

Nothing to flag here.
