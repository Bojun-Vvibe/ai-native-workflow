// good: suspend fun uses non-blocking awaits / withContext instead.
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext

suspend fun fetchUser(id: Long): String = withContext(Dispatchers.IO) {
    "user:$id"
}

suspend fun fetchTwo(a: Long, b: Long): Pair<String, String> = coroutineScope {
    val ra = async { fetchUser(a) }
    val rb = async { fetchUser(b) }
    ra.await() to rb.await()
}
