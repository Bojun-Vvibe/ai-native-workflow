package safe.e

// String-literal false positives — extraction and launch references
// occur only inside strings. The Kotlin-aware stripper blanks them.
class Strings {
    val a: String = "intent.getParcelableExtra<Intent>(\"next\")"
    val b: String = "startActivity(redirect)"
    val c: String = """
        Avoid: intent.getStringExtra("target")
        Avoid: startService(forward)
    """
}
