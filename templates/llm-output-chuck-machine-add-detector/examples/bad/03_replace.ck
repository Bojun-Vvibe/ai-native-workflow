// hot-swap a running shred with a runtime-chosen file.
0 => int currentID;
fun void swap(string nextFile) {
    Machine.replace(currentID, nextFile);
}
