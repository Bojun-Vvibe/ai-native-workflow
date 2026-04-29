use strict;
use warnings;

# heredoc looks like a string body but `do` is on its own line above.
my $msg = <<'END_DOC';
Beware: do $path will execute arbitrary perl from the file at $path.
Even require $module_name will do the same.
END_DOC

print $msg;

# real sink:
require "remote/$ARGV[0].pm";
