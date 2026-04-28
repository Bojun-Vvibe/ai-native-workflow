// bad: runBlocking inside one suspend fun, alongside a non-suspend sibling
import kotlinx.coroutines.runBlocking

fun helper(x: Int): Int {
    // not flagged here — this is a plain (non-suspend) fun
    return runBlocking { x }
}

suspend fun caller(x: Int): Int {
    val mid = helper(x)
    return runBlocking { mid + 1 }
}
