// bad: multiple runBlocking calls in one suspend fun
import kotlinx.coroutines.runBlocking

suspend fun pipeline(x: Int): Int {
    val a = runBlocking { x + 1 }
    val b = runBlocking { a * 2 }
    return b
}
