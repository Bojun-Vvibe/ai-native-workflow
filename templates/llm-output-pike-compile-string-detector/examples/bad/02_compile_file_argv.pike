// Loads a Pike file whose path comes from argv.
int main(int argc, array(string) argv) {
    program p = compile_file(argv[1]);
    p();
    return 0;
}
