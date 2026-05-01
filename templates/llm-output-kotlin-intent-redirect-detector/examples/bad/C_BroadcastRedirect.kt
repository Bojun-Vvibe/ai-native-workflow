package vuln.c

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class BroadcastRedirect : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val forward = intent.getParcelableExtra<Intent>("forward")
        context.sendBroadcast(forward)
    }
}
