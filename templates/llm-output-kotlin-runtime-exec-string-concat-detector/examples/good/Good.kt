// Safe forms — no interpolation or concatenation flowing into the sink.
package good

class Good {
    fun pingLocalhost() {
        Runtime.getRuntime().exec(arrayOf("ping", "-c", "1", "127.0.0.1"))
    }

    fun listFiles() {
        ProcessBuilder(listOf("ls", "-la", "/tmp")).start()
    }

    fun pingAllowed(host: String) {
        val allowed = setOf("a.example.test", "b.example.test")
        require(host in allowed)
        // argv form, no interpolation in the first element
        Runtime.getRuntime().exec(arrayOf("ping", "-c", "1", host))
    }

    fun staticCommand() {
        val pb = ProcessBuilder()
        pb.command("uptime")
        pb.start()
    }
}
