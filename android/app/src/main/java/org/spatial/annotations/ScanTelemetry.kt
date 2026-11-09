package org.spatial.annotations

import java.time.Instant
import java.util.UUID

/** Monotonic milliseconds only for durations. Wall time is a label, never subtracted. No note text or auth data. */
class ScanTelemetry(val environment: String, val method: String, val started: Long,
                    val testId: String = UUID.randomUUID().toString(), val timestamp: String = Instant.now().toString()) {
    var marker: String? = null
    var detected: Long? = null
    var frames: Int = 0
    var finished = false
        private set
    fun finish(now: Long, lookup: LookupTiming? = null, count: Int = 0, failure: String? = null): Map<String, Any?>? {
        if (finished) return null
        finished = true
        val optical = method == "camera_qr"
        return linkedMapOf(
            "test_id" to testId, "timestamp" to timestamp, "environment" to environment,
            "marker_uuid" to marker, "identification_method" to method,
            "recognition_success" to if (optical) (detected != null) else null,
            "frames_processed" to frames,
            "recognition_latency_ms" to if (optical) detected?.minus(started) else null,
            "recognition_wait_ms" to if (optical && detected == null) now - started else null,
            "backend_success" to lookup?.let { it.failure == null },
            "backend_latency_ms" to lookup?.let { it.completed - it.started },
            "detection_to_retrieval_ms" to if (optical) lookup?.let { result -> detected?.let { result.completed - it } } else null,
            "retrieval_to_ui_ms" to lookup?.let { now - it.completed },
            "total_latency_ms" to now - started, "annotation_count" to count,
            "failure_category" to (failure ?: lookup?.failure))
    }
}
data class LookupTiming(val started: Long, val completed: Long, val failure: String? = null)
