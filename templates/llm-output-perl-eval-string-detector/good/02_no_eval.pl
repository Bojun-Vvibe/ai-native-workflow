#!/usr/bin/perl
use strict; use warnings;

# The word "eval" appears only in a comment and a string literal.
# Neither should be flagged.
print "do not call eval on user input\n";
# Reminder: use eval { ... } not eval "...".
my $msg = 'eval "this string" would be unsafe';
print "$msg\n";
