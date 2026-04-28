// bad: suspend extension fun
import kotlinx.coroutines.runBlocking

suspend fun String.fetchSize(): Int {
    return runBlocking { this@fetchSize.length }
}
