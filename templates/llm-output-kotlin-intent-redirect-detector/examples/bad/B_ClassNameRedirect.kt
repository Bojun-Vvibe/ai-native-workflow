package vuln.b

import android.app.Activity
import android.content.Intent
import android.os.Bundle

class ClassNameRedirect : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val target = intent.getStringExtra("target_class")
        val redirect = Intent()
        redirect.setClassName(packageName, target ?: return)
        startActivityForResult(redirect, 1)
    }
}
