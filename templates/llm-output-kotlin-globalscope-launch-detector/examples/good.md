# Quick coroutine snippets — corrected

Same shapes as bad.md but using structured scopes. Detector should
report 0 findings.

## 1. viewModelScope owns the work

```kotlin
class UserViewModel(private val repo: UserRepo) : ViewModel() {
    fun save(user: User) {
        viewModelScope.launch {
            repo.persist(user)
        }
    }
}
```

## 2. coroutineScope makes parallel awaits cancel-safe

```kotlin
suspend fun loadDashboard(): Dashboard = coroutineScope {
    val a = async { fetchA() }
    val b = async { fetchB() }
    Dashboard(a.await(), b.await())
}
```

## 3. injected scope for the bridge

```kotlin
class PingService(private val scope: CoroutineScope) {
    fun pingAsync(): CompletableFuture<Pong> =
        scope.future { ping() }
}
```

## 4. supervisor scope for the counter actor

```kotlin
class Counter(private val scope: CoroutineScope) {
    fun start() = scope.actor<Int> {
        var sum = 0
        for (n in channel) sum += n
    }
}
```

## 5. caller-owned tick stream

```kotlin
fun CoroutineScope.ticks() = produce<Long> {
    while (isActive) {
        send(System.currentTimeMillis())
        delay(1000)
    }
}
```

## 6. main() bridge — explicitly opted in

```kotlin
fun main() = runBlocking {
    @OptIn(DelicateCoroutinesApi::class)
    GlobalScope.launch { warmCaches() }.join() // llm-detector: allow GlobalScope
}
```

The phrase "GlobalScope" in prose, in a // line comment, and in a
"GlobalScope.launch" string literal below should all be ignored.

```kotlin
val s = "GlobalScope.launch is the bad pattern"
val t = """
    GlobalScope.async multi-line example
""".trimIndent()
// GlobalScope.future would be wrong here too
```
