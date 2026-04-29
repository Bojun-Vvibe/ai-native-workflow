"good.st — none of these should trigger the detector."
| sum xs label compilerSymbol |

"Plain arithmetic — no eval anywhere."
sum := 0.
xs := #(1 2 3 4).
xs do: [:each | sum := sum + each].
Transcript show: sum printString; cr.

"All the dangerous identifiers mentioned only inside Smalltalk
 double-quote comments: Compiler evaluate:, OpalCompiler new
 evaluate, Smalltalk compileString:, RBParser parseExpression:,
 src asExpression — every one masked out."

"All the dangerous identifiers mentioned only inside string
 literals — note Smalltalk's doubled-apostrophe escape inside the
 literal."
label := 'see ''Compiler evaluate:'' and ''OpalCompiler new evaluate'' for details'.
Transcript show: label; cr.

"Reflection on the Compiler class symbol itself with no message
 send — not eval."
compilerSymbol := Compiler.
Transcript show: compilerSymbol printString; cr.

"Explicit suppression for a fixture-only path."
result := Compiler evaluate: '1 + 2'.   "eval-string-ok"
