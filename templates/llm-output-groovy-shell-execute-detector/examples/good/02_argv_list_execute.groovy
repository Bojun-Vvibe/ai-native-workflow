def branch = params.branch
def proc = ["git", "log", "-1", branch].execute()
proc.waitFor()
