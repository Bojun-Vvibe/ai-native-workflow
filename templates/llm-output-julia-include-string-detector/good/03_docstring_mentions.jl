"""
This module's docstring deliberately mentions include_string(mod, body)
and Core.eval(m, Meta.parse(body)) so we can verify the masker hides
references that live inside triple-quoted strings.
"""
module Doc

greet(name) = "hello, $(name)"

end
