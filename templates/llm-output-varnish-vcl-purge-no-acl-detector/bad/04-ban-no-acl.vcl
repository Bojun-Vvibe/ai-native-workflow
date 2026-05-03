vcl 4.1;

backend default {
    .host = "127.0.0.1";
    .port = "8080";
}

# bad: ban() invoked from vcl_recv with no acl gate
sub vcl_recv {
    if (req.method == "BAN") {
        ban("req.url ~ " + req.url);
        return (synth(200, "Banned"));
    }
}
