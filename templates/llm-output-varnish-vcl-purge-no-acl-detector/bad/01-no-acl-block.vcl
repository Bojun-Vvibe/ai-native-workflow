vcl 4.1;

backend default {
    .host = "127.0.0.1";
    .port = "8080";
}

# bad: PURGE handled with no acl block defined anywhere
sub vcl_recv {
    if (req.method == "PURGE") {
        return (purge);
    }
}
