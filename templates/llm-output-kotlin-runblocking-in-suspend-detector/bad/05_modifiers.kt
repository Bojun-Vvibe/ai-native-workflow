// bad: suspend fun with a suspend modifier far from the fun keyword
import kotlinx.coroutines.runBlocking

class Repo {
    public suspend inline fun query(sql: String): String {
        return runBlocking { "result($sql)" }
    }
}
