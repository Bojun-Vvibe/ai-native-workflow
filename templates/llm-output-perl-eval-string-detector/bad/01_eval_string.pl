#!/usr/bin/perl
use strict; use warnings;
my $mod = shift @ARGV;
eval "use $mod;";
die $@ if $@;
print "loaded $mod\n";
