#!/usr/bin/perl
use strict; use warnings;
my $name = $ARGV[0] // 'World';
eval qq(print "hello, $name\\n";);
