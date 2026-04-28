// good: triple-quoted raw string contains the literal text
// `runBlocking` but is masked by the scanner.
suspend fun docs(): String {
    val md = """
        ## Antipattern
        Do not use runBlocking { ... } from inside a suspend fun.
        Use withContext or coroutineScope.
    """.trimIndent()
    return md
}
