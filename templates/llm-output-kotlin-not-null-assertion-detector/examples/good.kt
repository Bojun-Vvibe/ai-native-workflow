package example

// Same intent, no `!!`. Nulls handled with ?., ?:, let, requireNotNull.

class UserRepo(private val cache: Map<String, String?>) {

    fun greet(id: String?): String {
        val key = requireNotNull(id) { "id required" }
        val raw = cache[key] ?: return "hi stranger"
        val first = raw.trim().split(" ").firstOrNull() ?: "friend"
        return "hi $first"
    }

    fun upper(s: String?): String {
        println("wow!!")            // string literal still fine
        return s?.uppercase() ?: ""
    }

    /* block !! still fine inside comments */
    fun parse(json: Any?): Map<String, Any> {
        @Suppress("UNCHECKED_CAST")
        return (json as? Map<String, Any>) ?: emptyMap()
    }
}
