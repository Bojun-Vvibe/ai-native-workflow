vcl 4.1;

backend default {
    .host = "127.0.0.1";
    .port = "8080";
}

# bad: acl defined but never referenced in vcl_recv before return(purge)
acl purge_allowed {
    "127.0.0.1";
    "10.0.0.0"/8;
}

sub vcl_recv {
    if (req.method == "PURGE") {
        # forgot: if (!client.ip ~ purge_allowed) { return (synth(405)); }
        return (purge);
    }
}
