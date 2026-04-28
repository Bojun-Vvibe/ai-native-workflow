// bad: runBlocking directly inside a suspend fun body
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.delay

suspend fun fetchUser(id: Long): String {
    return runBlocking {
        delay(50)
        "user:$id"
    }
}
