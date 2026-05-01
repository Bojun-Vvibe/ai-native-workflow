package vuln.a

import android.app.Activity
import android.content.Intent
import android.os.Bundle

class RedirectActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val next = intent.getParcelableExtra<Intent>("next")
        startActivity(next)
        finish()
    }
}
