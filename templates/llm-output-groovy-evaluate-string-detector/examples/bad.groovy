#!/usr/bin/env groovy
// Bad fixture: multiple Groovy dynamic-eval calls — each should be flagged.

// 1: classic Eval.me on a variable
def script = "1 + 2"
def r1 = Eval.me(script)

// 2: Eval.x with a parameter binding (still dynamic source)
def r2 = Eval.x(42, "x.toString().reverse()")

// 3: GroovyShell.evaluate on a variable
def shell = new GroovyShell()
def r3 = shell.evaluate(script)

// 4: GroovyShell inline new + .evaluate on the same line
def r4 = new GroovyShell().evaluate("System.getProperty('user.dir')")

// 5: GroovyShell run with a string source
new GroovyShell().run("println 'pwn'", "inline.groovy", [] as String[])

// 6: GroovyClassLoader.parseClass on dynamic text
def loader = new GroovyClassLoader()
def cls = loader.parseClass("class C { def go() { 'hi' } }")

// 7: Eval.xy two-bind variant
def r7 = Eval.xy("a", "b", "x + y")

// 8: triple-quoted source piped through Eval.me — the call site still flags
def src = """def f(){ 'still dynamic' }; f()"""
def r8 = Eval.me(src)
