vcl 4.1;

backend default {
    .host = "127.0.0.1";
    .port = "8080";
}

# good: BAN gated by acl check
acl ban_allowed {
    "127.0.0.1";
    "192.168.10.0"/24;
}

sub vcl_recv {
    if (req.method == "BAN") {
        if (!client.ip ~ ban_allowed) {
            return (synth(403, "forbidden"));
        }
        ban("req.url ~ " + req.url);
        return (synth(200, "Banned"));
    }
}
