package Loader;
use strict; use warnings;

sub load_plugin {
    my ($name) = @_;
    eval("require $name; $name->import();");
    return !$@;
}

1;
