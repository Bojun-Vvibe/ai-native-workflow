package safe.c

import android.app.PendingIntent
import android.content.Context
import android.content.Intent

class ImmutablePending(val ctx: Context, val incoming: Intent) {
    fun build(): PendingIntent {
        val inner = incoming.getParcelableExtra<Intent>("inner")
        return PendingIntent.getActivity(
            ctx, 0, inner, PendingIntent.FLAG_IMMUTABLE
        )
    }
}
