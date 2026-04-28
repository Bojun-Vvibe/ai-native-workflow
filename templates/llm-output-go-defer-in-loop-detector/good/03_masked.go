package main

// Comment that says "defer in for loop" inside a comment must NOT trigger.
// Likewise a string literal mentioning `defer` inside `for` must not.

func tricky() {
	msg := "remember: defer inside for is bad"
	_ = msg
	for i := 0; i < 10; i++ {
		_ = i
	}
	defer cleanup() // function-level defer, AFTER the for loop closes
}

func cleanup() {}
