#!/usr/bin/perl
use strict;
use warnings;
use IPC::Open3;
use Symbol qw(gensym);

my $path = shift @ARGV;
my $branch = $ENV{BRANCH} // 'main';

# Good #1: list-form system — no shell, no injection.
system('git', 'log', '--', $path) == 0
    or die "git log failed: $?";

# Good #2: list-form exec for the no-return case.
# (Wrapped in fork so this script keeps running.)
if (fork() == 0) {
    exec('git', 'diff', $branch, '--', $path);
    die "exec failed: $!";
}

# Good #3: 3-arg open with explicit mode + list form.
open(my $fh, '-|', 'git', 'log', '--', $path) or die "open: $!";
while (my $line = <$fh>) {
    print $line;
}
close $fh;

# Good #4: backticks with a pure literal — no interpolation, so the
# detector should NOT fire (and the shape is widely understood).
my $version = `git --version`;

# Good #5: single-quoted strings are not interpolated.
system('echo', 'literal $path');

# Good #6: documentation strings that mention the bad shape must NOT
# trip the detector — they live inside string literals.
my $advice = "do not write `git log -- \$path` in production";
my $note   = 'system("rm -rf $path/build") — never do this';
