#!/usr/bin/perl
use strict; use warnings;
my $expr = '1 + 2 * 3';
my $val = eval $expr;
print "got $val\n";
