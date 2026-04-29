# Good: mention of eval(" inside a string literal must not trigger
doc = "Avoid eval('...') and new Function('...') for user input."
console.log doc
warn = 'Function("x") on tainted data is unsafe.'
console.log warn
hint = """
Note: setTimeout "code", 1000 is the same anti-pattern as eval.
"""
console.log hint
