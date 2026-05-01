#!/usr/bin/perl
use strict;
use warnings;

my $path = shift @ARGV;
my $branch = $ENV{BRANCH} // 'main';

# Bad #1: backticks with interpolation.
my $log = `git log -- $path`;

# Bad #2: qx{} with interpolation.
my $diff = qx{git diff $branch -- $path};

# Bad #3: qx// with generic delimiter and interpolation.
my $blame = qx/git blame -L 1,10 $path/;

# Bad #4: system() called with one interpolated string.
system("rm -rf $path/build");

# Bad #5: parenthesis-less system with interpolation.
system "tar czf backup-$branch.tgz $path";

# Bad #6: exec() with interpolated string.
exec("ssh user\@$ENV{HOST} ls $path");

# Bad #7: two-arg open with pipe + interpolation.
open(my $fh, "git log $path|") or die "open: $!";
while (my $line = <$fh>) {
    print $line;
}
close $fh;
