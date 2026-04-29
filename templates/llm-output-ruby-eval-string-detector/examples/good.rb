#!/usr/bin/env ruby
# Good fixture: zero findings expected.

# 1: block-form instance_eval — closure, not a string. Safe.
obj.instance_eval do
  @x = compute
end

# 2: block-form class_eval with `{ ... }`. Safe.
klass.class_eval { define_method(:greet) { "hi" } }

# 3: a method NAMED `evaluate` is not flagged.
def evaluate(expr)
  expr.to_i * 2
end

# 4: `eval` in a comment is masked: eval "danger"
# eval "this is inside a comment"

# 5: the literal string "eval" is masked: warn("call eval('x') is bad")

# 6: define_method is the safe replacement for class_eval-with-string.
klass.define_method(:greet) { |name| "hello #{name}" }

# 7: public_send is the safe replacement for eval-of-method-name.
obj.public_send(method_name, *args)

# 8: audited line, suppressed.
eval(audited_constant) # eval-ok — reviewed by SecOps 2026-04-15
