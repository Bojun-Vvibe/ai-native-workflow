vcl 4.1;

backend default {
    .host = "127.0.0.1";
    .port = "8080";
}

# good: acl defined, checked before return(purge)
acl purge {
    "127.0.0.1";
    "10.0.0.0"/8;
}

sub vcl_recv {
    if (req.method == "PURGE") {
        if (!client.ip ~ purge) {
            return (synth(405, "Not allowed"));
        }
        return (purge);
    }
}
