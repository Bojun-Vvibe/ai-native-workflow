def cmd = "ping -c 1 " + request.getParameter("host")
def proc = Runtime.getRuntime().exec(cmd)
proc.waitFor()
