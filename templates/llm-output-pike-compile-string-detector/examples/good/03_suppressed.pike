// Suppression marker: author asserts this is a trusted snippet.
int main() {
    string trusted = "int main() { write(\"ok\\n\"); return 0; }";
    program p = compile_string(trusted, "trusted.pike");  // pike-eval-ok
    p();
    return 0;
}
