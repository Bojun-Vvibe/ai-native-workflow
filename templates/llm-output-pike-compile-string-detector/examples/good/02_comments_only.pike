// Comments mention compile_string("evil " + x) and compile_file(p)
// but no runtime evaluation actually happens.
/* compile_string(src) -- documented elsewhere, never called here. */
int main() {
    // We could call compile_string(src) here, but we will not.
    write("hello, world\n");
    return 0;
}
