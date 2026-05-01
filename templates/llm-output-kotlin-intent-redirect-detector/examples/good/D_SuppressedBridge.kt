package safe.d

// Inline-suppressed redirect: a deliberate, reviewed bridge to a
// well-known internal screen. Single line opts out of the gate.
import android.app.Activity
import android.content.Intent
import android.os.Bundle

class SuppressedBridge : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val next = intent.getParcelableExtra<Intent>("next") // intent-ok
        startActivity(next) // intent-ok
    }
}
