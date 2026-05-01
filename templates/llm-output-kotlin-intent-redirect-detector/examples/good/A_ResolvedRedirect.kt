package safe.a

import android.app.Activity
import android.content.Intent
import android.os.Bundle

class ResolvedRedirect : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val next = intent.getParcelableExtra<Intent>("next") ?: return
        val info = next.resolveActivity(packageManager)
        if (info != null && info.packageName == "com.example.allowed") {
            startActivity(next)
        }
        finish()
    }
}
