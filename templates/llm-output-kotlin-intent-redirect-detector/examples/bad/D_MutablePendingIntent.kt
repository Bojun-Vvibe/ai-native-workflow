package vuln.d

import android.app.PendingIntent
import android.content.Context
import android.content.Intent

class MutablePendingIntent(val ctx: Context) {
    fun build(): PendingIntent {
        val inner = ctx.intent.getParcelableExtra<Intent>("inner")
        return PendingIntent.getActivity(ctx, 0, inner, 0)
    }
}

private val Context.intent: Intent get() = error("test stub")
