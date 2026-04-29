// Pure data transformation, no compile / cpp anywhere.
int main(int argc, array(string) argv) {
    array(string) lines = Stdio.read_file(argv[1])/"\n";
    int total = 0;
    foreach (lines, string line) {
        array parts = line/",";
        if (sizeof(parts) >= 2) {
            total += (int)parts[1];
        }
    }
    write("sum: %d\n", total);
    return 0;
}
