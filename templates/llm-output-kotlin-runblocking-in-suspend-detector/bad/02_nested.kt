// bad: nested deep inside a suspend fun's control flow
import kotlinx.coroutines.runBlocking

suspend fun loadAll(ids: List<Long>): List<String> {
    val out = mutableListOf<String>()
    for (id in ids) {
        if (id > 0) {
            val v = runBlocking { "id=$id" }
            out.add(v)
        }
    }
    return out
}
