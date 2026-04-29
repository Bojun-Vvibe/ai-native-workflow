#!/usr/bin/env ruby
# Bad fixture: each line should be flagged by the ruby-eval-string detector.

eval "puts #{user_input}"                              # 1: double-quoted interpolation into eval
eval('puts ' + cmd)                                    # 2: concatenated string into eval()
instance_eval "@x = #{value}"                          # 3: instance_eval with a string
klass.class_eval("def #{name}; #{body}; end")          # 4: class_eval with a string
Mod.module_eval(snippet)                               # 5: module_eval with a bareword (likely-string var)
binding.eval(expr)                                     # 6: binding.eval on a variable
Kernel.eval %q{system("rm -rf /")}                     # 7: %q literal into Kernel.eval
TOPLEVEL_BINDING.eval("$LOAD_PATH << dir")             # 8: literal into TOPLEVEL_BINDING.eval
eval `cat /tmp/payload.rb`                             # 9: backtick command output into eval
obj.instance_eval(<<~RUBY)                             # 10: heredoc into instance_eval
  do_stuff(#{arg})
RUBY
