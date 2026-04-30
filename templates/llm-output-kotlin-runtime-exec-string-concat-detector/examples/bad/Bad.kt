// CWE-78: OS command injection via Runtime.exec / ProcessBuilder + interpolation.
// Every site below should be flagged by the detector.

package vuln

class Bad {
    fun ping1(host: String) {
        Runtime.getRuntime().exec("ping -c 1 " + host)
    }

    fun ping2(host: String) {
        Runtime.getRuntime().exec("ping -c 1 $host")
    }

    fun ping3(host: String) {
        Runtime.getRuntime().exec(arrayOf("sh", "-c", "ping -c 1 $host"))
    }

    fun ping4(host: String) {
        ProcessBuilder("ping -c 1 $host").start()
    }

    fun ping5(host: String) {
        ProcessBuilder(listOf("sh", "-c", "ping -c 1 $host")).start()
    }

    fun ping6(host: String) {
        val pb = ProcessBuilder()
        pb.command("ping -c 1 $host")
        pb.start()
    }

    fun ping7(host: String) {
        Runtime.getRuntime().exec("curl https://example.test/" + host + "/profile")
    }

    fun ping8(host: String) {
        ProcessBuilder(arrayOf("sh", "-c", "echo " + host).toList()).start()
    }
}
