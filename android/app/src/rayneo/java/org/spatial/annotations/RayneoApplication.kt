package org.spatial.annotations

import android.app.Application
import com.ffalcon.mercury.android.sdk.MercurySDK

class RayneoApplication : Application() {
    override fun onCreate() { super.onCreate(); MercurySDK.init(this) }
}
