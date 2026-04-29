# Pipe `print` output through a runtime command - classic shell-pipe RCE
# if `tag` flows from user input.
tag = "ABCD"
set print "|tee log-".tag.".txt"
print "started"
plot x*x
