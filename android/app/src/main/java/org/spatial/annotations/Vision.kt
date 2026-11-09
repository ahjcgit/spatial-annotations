package org.spatial.annotations

import com.google.gson.annotations.SerializedName

/** Box is normalized xyxy in the EXIF-corrected image uploaded to the backend. */
data class Detection(val label: String, val confidence: Float, val box: List<Float>) {
    fun valid() = label.isNotBlank() && confidence.isFinite() && confidence in 0f..1f &&
        box.size == 4 && box.all { it.isFinite() && it in 0f..1f } && box[0] < box[2] && box[1] < box[3]
}
data class VisionResult(val model: String, val width: Int, val height: Int,
    @SerializedName("inference_ms") val inferenceMs: Double, val detections: List<Detection>)
