// Strings that mention "import 'dart:mirrors'" and ".invoke(" but
// only as documentation, not real code.
const help = "Do NOT use import 'dart:mirrors'; it breaks AOT.";
const note = "Methods like .invoke( and .newInstance( are mirror APIs.";

void main() {
  print(help);
  print(note);
}
