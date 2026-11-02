package org.spatial.annotations

// A tracked pose must specify a frame, monotonic timestamp and tracking validity.
// The fallback never supplies a fabricated pose or treats 2D QR pixels as an anchor.
data class Pose(val positionMeters: FloatArray, val rotationXyzw: FloatArray, val timestampNanos: Long, val frame: String)
interface SpatialTracker { fun headPose(): Pose?; val status: String }
class UnavailableSpatialTracker : SpatialTracker {
    override fun headPose(): Pose? = null
    override val status = "Screen-space panel · spatial tracking unavailable"
}
interface AnnotationRenderer { fun render(state: AnnotationState) }
enum class DeviceAction { SELECT, BACK, NEXT, PREVIOUS, DETAILS }
interface DeviceInput { fun actionForKey(keyCode: Int): DeviceAction? }
class StandardDeviceInput : DeviceInput {
    override fun actionForKey(keyCode: Int): DeviceAction? = when (keyCode) {
        23, 66 -> DeviceAction.SELECT // DPAD_CENTER, ENTER
        4 -> DeviceAction.BACK
        22, 20 -> DeviceAction.NEXT
        21, 19 -> DeviceAction.PREVIOUS
        62 -> DeviceAction.DETAILS // SPACE
        else -> null
    }
}
