// good: the string "runBlocking" appears only inside a string literal
// and inside a comment — must NOT trigger.
import kotlinx.coroutines.delay

// historical: this fun used runBlocking { ... } before 2.0
suspend fun docOnly(id: Long): String {
    val warn = "do not call runBlocking from suspend fun"
    delay(1)
    return "$warn id=$id"
}
