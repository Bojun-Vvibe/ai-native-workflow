#!/usr/bin/perl
use strict;
use warnings;

=pod

This POD block deliberately mentions `do $path` and `require $foo` and
`do qq{plugins/$name.pl}` so the masker has to skip over them.

=cut

# real sink is here, after the POD ends:
my $script = $ARGV[0];
do $script;
