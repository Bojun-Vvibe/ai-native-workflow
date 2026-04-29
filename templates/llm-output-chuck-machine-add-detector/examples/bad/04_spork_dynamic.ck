// fork another runtime-chosen file
"voice_" + me.arg(0) + ".ck" => string voicePath;
Machine.spork(voicePath);
