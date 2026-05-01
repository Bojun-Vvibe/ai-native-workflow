def branch = params.branch
def cmdArr = ["git", "log", "-1", branch] as String[]
Runtime.getRuntime().exec(cmdArr)
