package safe.b

import android.app.Activity
import android.content.Intent
import android.os.Bundle

class HardcodedDestination : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Argument key read for telemetry only; destination is hard-coded.
        val arg = intent.getStringExtra("arg")
        val redirect = Intent()
        redirect.setClassName("com.example.app", "com.example.app.InternalScreen")
        redirect.putExtra("arg", arg)
        startActivity(redirect)
    }
}
