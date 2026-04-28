// good: runBlocking in tests / non-suspend setup is allowed by this
// detector (there is no enclosing `suspend fun`).
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.delay

class FetcherTest {
    fun testFetchSync() {
        // plain (non-suspend) test entry: runBlocking is the bridge
        val v = runBlocking { delay(1); 42 }
        check(v == 42)
    }
}
