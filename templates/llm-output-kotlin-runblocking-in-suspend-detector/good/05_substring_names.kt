// good: identifier substring `runBlockingX` is not the runBlocking
// keyword and must NOT trigger.
suspend fun runBlockingXHelper(): Int = 1

suspend fun caller(): Int {
    val a = runBlockingXHelper()
    val b = myRunBlocking()
    return a + b
}

suspend fun myRunBlocking(): Int = 2
