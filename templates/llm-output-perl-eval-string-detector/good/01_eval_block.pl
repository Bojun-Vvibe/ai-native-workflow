#!/usr/bin/perl
use strict; use warnings;

# Safe: block form is try/catch, not string-eval.
my $result = eval {
    open(my $fh, '<', '/etc/hostname') or die "open: $!";
    my $line = <$fh>;
    close $fh;
    chomp $line;
    return $line;
};
if ($@) {
    warn "failed: $@";
} else {
    print "host=$result\n";
}
