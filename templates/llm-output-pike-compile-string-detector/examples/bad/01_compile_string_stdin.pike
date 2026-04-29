// Reads Pike source from stdin and runs it.
int main() {
    string src = Stdio.stdin->read();
    program p = compile_string(src);
    p();
    return 0;
}
