component {
    public void function runIt() {
        cfexecute(name="/bin/sh", arguments="-c " & arguments.cmd, timeout=5);
    }
}
