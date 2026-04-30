"""Legacy commands.getoutput with concatenation."""
import commands

out = commands.getoutput("ls -la " + dirpath)
status, text = commands.getstatusoutput("stat " + filename)
