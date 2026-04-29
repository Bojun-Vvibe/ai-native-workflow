#!/usr/bin/perl
use strict;
use warnings;

# This whole file's purpose is to *talk about* the sinks in comments.
# Examples we deliberately mention but never call:
#   do $path
#   do "plugins/$name.pl"
#   do qq{addons/$tag.pl}
#   require $mod
#   require "Foo/$x.pm"
# None of the above should be flagged because they are all in line comments.

sub greet { return "hi, $_[0]" }
print greet("world"), "\n";
