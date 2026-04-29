#!/usr/bin/env groovy
// Good fixture: zero findings expected.

// 1: a method literally named `evaluate` on a non-shell receiver — not flagged
class Scorer {
    def evaluate(int n) { n * 2 }
}
def s = new Scorer()
println s.evaluate(21)

// 2: a comment that happens to contain Eval.me("x") — masked, not flagged
// e.g. Eval.me("dangerous") is the thing we are NOT doing here

// 3: a string literal containing "GroovyShell().evaluate" — masked
def warning = "do not call new GroovyShell().evaluate(input) in prod"
println warning

// 4: dispatch table instead of Eval.me — the safe pattern
def ops = [
    'square': { int n -> n * n },
    'cube':   { int n -> n * n * n },
]
println ops['square'](7)

// 5: a variable named `evaluator` — not a shell, not flagged
def evaluator = [run: { x -> x + 1 }]
println evaluator.run(10)

// 6: GroovyShell mentioned only in a string — masked
def doc = "GroovyShell is unsafe; do not use shell.evaluate(src)"
println doc

// 7: an audited Eval.me line, suppressed explicitly
def ok = Eval.me("1+1")  // groovy-eval-ok — sandboxed by SecureASTCustomizer above
println ok

// 8: parseClass mentioned only in a /* ... */ block comment
/* note: avoid loader.parseClass(userInput) */
println "done"
