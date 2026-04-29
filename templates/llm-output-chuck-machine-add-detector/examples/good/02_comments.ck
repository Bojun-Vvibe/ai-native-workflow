// historical note: the previous version used Machine.add("legacy.ck")
// but that was replaced with a static dispatch table.
/* TODO: revisit Machine.replace(id, path) once the new audio graph
   lands. For now we use direct shred wiring. */
SinOsc s => dac;
440 => s.freq;
1::second => now;
