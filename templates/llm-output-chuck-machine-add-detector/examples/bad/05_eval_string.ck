// direct ChucK source evaluated from a string -- pure eval sink.
"SinOsc s => dac; 440 => s.freq; 1::second => now;" => string code;
Machine.eval(code);
