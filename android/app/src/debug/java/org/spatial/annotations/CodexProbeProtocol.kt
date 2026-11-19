package org.spatial.annotations

data class ProbeLabel(val identity: String, val label: String, val uncertain: Boolean, val side: String = "unknown")
data class ProbeResponse(val requestId: String, val sourceSha256: String, val labels: List<ProbeLabel>)

/** Snapshot-only protocol: no UUID assignment, note retrieval or unbounded stale display. */
object CodexProbeProtocol {
    const val MAX_SOURCE_AGE_NS = 120_000_000_000L
    const val DISPLAY_DURATION_MS = 30_000L
    fun validate(response: ProbeResponse, expectedId: String, expectedHash: String, ageNs: Long) {
        require(response.requestId == expectedId && expectedId.isNotBlank()) { "request_id_mismatch" }
        require(response.sourceSha256 == expectedHash && expectedHash.matches(Regex("[a-f0-9]{64}"))) { "source_hash_mismatch" }
        require(ageNs in 0..MAX_SOURCE_AGE_NS) { "source_expired" }
        require(response.labels.size <= 2) { "too_many_labels" }
        require(response.labels.map { it.identity }.distinct().size == response.labels.size) { "duplicate_identity" }
        response.labels.forEach {
            require(it.identity in listOf("A", "B")) { "unknown_identity" }
            require(it.side in listOf("left", "right", "center", "unknown")) { "invalid_side" }
            require(it.label.length in 1..48 && it.label.none { c -> c.isISOControl() }) { "invalid_label" }
        }
    }
}
