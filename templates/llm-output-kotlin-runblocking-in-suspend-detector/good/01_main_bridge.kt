// good: runBlocking only in a `main` (non-suspend) entry point — the
// canonical bridge from blocking-world into coroutine-world.
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.delay

fun main() = runBlocking {
    delay(10)
    println("started")
}
