// path is concatenated from external input -- classic code-load sink.
fun void loadPatch(string name) {
    Machine.add("patches/" + name + ".ck");
}
