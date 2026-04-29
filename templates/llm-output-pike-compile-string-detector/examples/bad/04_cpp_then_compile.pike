// Hands a CPP-expanded blob to compile().
int main() {
    string blob = Stdio.read_file("snippet.h");
    string expanded = cpp(blob, "snippet.h");
    program p = compile(expanded);
    p();
    return 0;
}
