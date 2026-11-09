package org.spatial.annotations

interface AnnotationRenderer { fun render(state: AnnotationState) }
enum class DeviceAction { SELECT, BACK, NEXT, PREVIOUS, DETAILS }
interface DeviceInput { fun actionForKey(keyCode: Int): DeviceAction? }
class StandardDeviceInput : DeviceInput {
    override fun actionForKey(keyCode: Int): DeviceAction? = when (keyCode) {
        23, 66 -> DeviceAction.SELECT // DPAD_CENTER, ENTER
        4 -> DeviceAction.BACK
        22 -> DeviceAction.NEXT
        21 -> DeviceAction.PREVIOUS
        62 -> DeviceAction.DETAILS // SPACE
        else -> null
    }
}
