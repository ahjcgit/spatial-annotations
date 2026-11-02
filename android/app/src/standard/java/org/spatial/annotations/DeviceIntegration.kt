package org.spatial.annotations

import android.app.Activity

object DeviceIntegration {
    const val description = "Standard Android · Mercury SDK unavailable"
    fun launch(activity: Activity): Boolean = false
}
