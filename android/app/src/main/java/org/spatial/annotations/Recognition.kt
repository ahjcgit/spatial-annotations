package org.spatial.annotations

import com.google.zxing.*
import com.google.zxing.common.HybridBinarizer
import java.util.Locale

object MarkerId {
    private val canonical = Regex("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
    fun parse(payload: String): String? {
        val id = payload.trim().removePrefix("spatial:v1:")
        return id.takeIf { canonical.matches(it) }?.lowercase(Locale.ROOT)
    }
    fun payload(id: String): String = "spatial:v1:" + requireNotNull(parse(id))
}

// Packed luminance, not RGB; no camera images leave the device.
data class CameraFrame(val luminance: ByteArray, val width: Int, val height: Int, val timestampNanos: Long, val sensorRotation: Int = 0)
data class ObjectIdentity(val markerId: String, val confidence: Float, val source: String, val points: List<ImagePoint> = emptyList())
interface ObjectRecognizer { fun recognize(frame: CameraFrame): ObjectIdentity? }
interface CameraCapture { fun start(onFrame: (CameraFrame) -> Unit, onStatus: (String) -> Unit); fun stop() }

class QrObjectRecognizer : ObjectRecognizer {
    private val reader = MultiFormatReader().apply {
        setHints(mapOf(DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE), DecodeHintType.TRY_HARDER to true))
    }
    @Synchronized override fun recognize(frame: CameraFrame): ObjectIdentity? {
        if (frame.width <= 0 || frame.height <= 0 || frame.luminance.size.toLong() != frame.width.toLong() * frame.height) return null
        val source = PlanarYUVLuminanceSource(frame.luminance, frame.width, frame.height, 0, 0, frame.width, frame.height, false)
        return try {
            val result = reader.decodeWithState(BinaryBitmap(HybridBinarizer(source)))
            if (!result.text.startsWith("spatial:v1:")) null else MarkerId.parse(result.text)?.let {
                ObjectIdentity(it, 1f, "QR", FrameGeometry.validPoints(
                    result.resultPoints.orEmpty().filterNotNull().map { point -> ImagePoint(point.x, point.y) }, frame.width, frame.height))
            }
        } catch (_: ReaderException) { null } finally { reader.reset() }
    }
}

// Simulation deliberately bypasses optical recognition and is labeled by the UI.
class SimulatedRecognizer(private val markerId: String) : ObjectRecognizer {
    override fun recognize(frame: CameraFrame) = MarkerId.parse(markerId)?.let { ObjectIdentity(it, 1f, "SIMULATION") }
}

object CameraPermissionPolicy {
    enum class Action { START_CAMERA, REQUEST_PERMISSION, SHOW_SETTINGS }
    fun action(granted: Boolean, askedBefore: Boolean, shouldShowRationale: Boolean): Action = when {
        granted -> Action.START_CAMERA
        !askedBefore || shouldShowRationale -> Action.REQUEST_PERMISSION
        else -> Action.SHOW_SETTINGS
    }
}

class LookupGate(private val intervalMillis: Long = 10_000) {
    private var marker: String? = null
    private var lastAt = Long.MIN_VALUE
    fun accept(id: String, nowMillis: Long): Boolean {
        if (id == marker && nowMillis - lastAt < intervalMillis) return false
        marker = id; lastAt = nowMillis; return true
    }
    fun reset() { marker = null; lastAt = Long.MIN_VALUE }
}
