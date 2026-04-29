"bad.st — every non-comment line below should trigger the detector."
| src result obj |

src := 'Transcript show: ''hi''; cr'.

"bad-1: classic Compiler evaluate:"
result := Compiler evaluate: src.

"bad-2: Compiler evaluate:for:"
result := Compiler evaluate: src for: obj.

"bad-3: OpalCompiler chain ending in evaluate"
result := OpalCompiler new source: src; evaluate.

"bad-4: Smalltalk compiler evaluate:"
result := Smalltalk compiler evaluate: src.

"bad-5: Smalltalk compileString:"
Smalltalk compileString: src.

"bad-6: asExpression Pharo idiom"
result := src asExpression.

"bad-7: RBParser parseExpression:"
result := RBParser parseExpression: src.

"bad-8: Parser new parse:"
result := Parser new parse: src class: UndefinedObject.

"bad-9: SmaCCParser parse:"
result := SmaCCParser parse: src.

"bad-10: ClassBuilder runtime compile:"
result := ClassBuilder new compile: 'foo ^ 1'.

"bad-11: string-evaluate heuristic — literal + evaluate on same line"
result := '1 + 2' evaluate.
