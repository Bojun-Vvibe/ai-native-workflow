#!/usr/bin/perl
use strict;
use warnings;

# LLM-generated dispatcher: take a path off the command line and `do` it.
my $path = $ARGV[0];
my $rv = do $path;
die "load failed: $@" if $@;
print "loaded: $rv\n";
