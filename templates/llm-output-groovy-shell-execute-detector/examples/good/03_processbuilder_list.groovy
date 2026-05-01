def branch = params.branch
def pb = new ProcessBuilder(["git", "checkout", branch])
pb.start().waitFor()
