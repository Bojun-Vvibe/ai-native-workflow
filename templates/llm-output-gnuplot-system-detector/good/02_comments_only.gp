# Comments mention dangerous calls but they are masked.
# We could use system("date") here but we are not.
# Avoid eval() and `hostname` - keep it static.
# load and call are the eval-of-a-file sinks; don't use them with vars.
set title "static title"
plot sin(x)
