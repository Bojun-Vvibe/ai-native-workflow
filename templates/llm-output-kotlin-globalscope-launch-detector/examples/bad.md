# Quick coroutine snippets

Five quick Kotlin snippets I asked the model for. All of them reach
for `GlobalScope` — that is the smell we want flagged.

## 1. fire-and-forget save in a ViewModel

```kotlin
class UserViewModel(private val repo: UserRepo) {
    fun save(user: User) {
        GlobalScope.launch {
            repo.persist(user)
        }
    }
}
```

## 2. parallel async without a scope

```kotlin
suspend fun loadDashboard(): Dashboard {
    val a = GlobalScope.async { fetchA() }
    val b = GlobalScope.async { fetchB() }
    return Dashboard(a.await(), b.await())
}
```

## 3. CompletableFuture bridge

```kotlin
fun pingAsync(): CompletableFuture<Pong> =
    GlobalScope.future { ping() }
```

## 4. legacy actor for a counter

```kotlin
fun counterActor() = GlobalScope.actor<Int> {
    var sum = 0
    for (n in channel) sum += n
}
```

## 5. produce-style stream

```kotlin
fun ticks() = GlobalScope.produce<Long> {
    while (isActive) {
        send(System.currentTimeMillis())
        delay(1000)
    }
}
```

The string "GlobalScope.launch" appears in this prose — that is fine,
only matches inside ```kotlin fences count.
