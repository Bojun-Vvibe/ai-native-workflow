// other Machine methods that do NOT load code: we don't flag them.
Machine.crash();    // pretend method, not a code-load sink
Machine.realtime(); // also fine
Machine.intsize();
