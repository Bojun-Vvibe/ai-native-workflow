// Concatenates user input into the source string.
int main() {
    string name = Stdio.stdin->gets();
    string src = "int main() { write(\"hello, " + name + "\\n\"); return 0; }";
    program p = compile_string(src, "user.pike");
    p();
    return 0;
}
