def target = args[0]
def pb = new ProcessBuilder("git clone " + target).start()
pb.waitFor()
