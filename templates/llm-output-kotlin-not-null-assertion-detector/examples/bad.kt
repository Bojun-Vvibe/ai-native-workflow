package example

// LLM-generated Kotlin riddled with `!!`. Compiles fine, NPEs in prod.

class UserRepo(private val cache: Map<String, String?>) {

    fun greet(id: String?): String {
        val raw = cache[id!!]!!                  // two !! on one line
        val name = raw.trim()!!                  // pointless !! after trim
        val first = name.split(" ").firstOrNull()!!
        return "hi $first"
    }

    fun upper(s: String?): String {
        // string literal "wow!!" must NOT be flagged
        println("wow!!")
        // // comment with !! must NOT be flagged
        return s!!.uppercase()
    }

    /* block !! must NOT be flagged either */
    fun parse(json: Any?): Map<String, Any> {
        return (json as? Map<String, Any>)!!
    }
}
