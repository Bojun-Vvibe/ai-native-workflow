# llm-output-scala-akka-actor-blocking-call-detector

Detect blocking calls inside Akka actor message handlers in LLM-emitted
Scala code.

## Why

LLMs writing Akka classic / typed actors frequently emit blocking calls
(`Await.result`, `Thread.sleep`, `CountDownLatch.await`, …) inside the
body of `receive` / `Behaviors.receiveMessage` / `onMessage`. Blocking
the actor thread starves the dispatcher, deadlocks the `ActorSystem`
under load, and defeats Akka's back-pressure model. The Akka docs are
explicit: never block in an actor; pipe `Future` results back with
`pipeTo(self)`, or move the blocking work to a dedicated dispatcher.

## What it flags

A line in a `.scala` / `.sc` file that **both**:

1. Sits inside what looks like an actor handler region — opened by one of:
   - `def receive[Command|Recover]: Receive`
   - `Behaviors.receive` / `Behaviors.receiveMessage` / `Behaviors.receivePartial`
   - `onMessage(...)` (typed actor `OnMessage` handler)
   - `Receive { ... }` partial-function literal
2. Calls a known blocking sink:
   - `Await.result`, `Await.ready`
   - `Thread.sleep`
   - `concurrent.blocking` / `scala.concurrent.blocking`
   - `CountDownLatch...await`
   - `BlockingQueue...take` / `BlockingQueue...put`
   - trailing `.get()` (sync await on `Future` / `CompletableFuture`)

Region tracking is brace-depth-based and scoped per file. Files with no
actor header are skipped entirely so utility code is not flagged.

## What it does NOT flag

- Blocking calls outside any actor handler (`main`, companions, helpers).
- Lines suffixed with `// blocking-ok` (per-line opt-out).
- Sinks inside `//` comments or string literals.

## Usage

```bash
python3 detect.py path/to/src
```

Exit code 1 if findings, 0 otherwise. Pure python3 stdlib.

## Worked example

```bash
./verify.sh
```

Should print `PASS` with `bad findings: >=5` and `good findings: 0`.

## Suppression

Append `// blocking-ok` to the offending line if the actor genuinely
runs on a dedicated blocking dispatcher.
