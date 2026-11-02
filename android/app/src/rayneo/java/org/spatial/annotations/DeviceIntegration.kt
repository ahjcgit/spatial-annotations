package org.spatial.annotations

import android.app.Activity
import android.content.Intent

object DeviceIntegration {
    const val description = "RayNeo Mercury adapter · hardware validation required"
    fun launch(activity: Activity): Boolean { activity.startActivity(Intent(activity, RayneoActivity::class.java)); return true }
}
