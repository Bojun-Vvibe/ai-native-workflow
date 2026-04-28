#!/usr/bin/perl
use strict; use warnings;
my $user_code = <STDIN>;
chomp $user_code;
eval $user_code;
print "ran\n";
