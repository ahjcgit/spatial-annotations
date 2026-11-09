package org.spatial.annotations

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

class ScanController(private val repository: AnnotationRepository, private val scope: CoroutineScope,
                     private val now: () -> Long = { System.nanoTime() / 1_000_000 }) {
    private val mutable = MutableStateFlow(AnnotationState())
    val state = mutable.asStateFlow()
    private var request: Job? = null
    private var revision = 0
    private val gate = LookupGate()
    fun markerSeen(marker: String, nowMillis: Long) { if (gate.accept(marker, nowMillis)) lookup(marker) }
    fun lookup(marker: String) {
        val valid = MarkerId.parse(marker) ?: run { clear("Invalid marker ID"); return }
        request?.cancel(); val current = ++revision
        mutable.value = AnnotationState(markerId = valid, loading = true, message = "Looking up object…")
        val started = now()
        request = scope.launch {
            try {
                val obj = repository.lookup(valid)
                val annotations = repository.annotations(obj.id)
                if (current == revision) mutable.value = AnnotationState(valid, obj, annotations, message = "${annotations.size} authorized notes${if (annotations.size == 100) " · More available" else ""}", lookupTiming = LookupTiming(started, now()))
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (current == revision) mutable.value = AnnotationState(markerId = valid, message = if (e is ApiException && e.code == 404) "Unknown object. Register it or use the companion." else e.message ?: "Network unavailable", unknown = e is ApiException && e.code == 404,
                    lookupTiming = LookupTiming(started, now(), if (e is ApiException) "http_${e.code}" else "network"))
            }
        }
    }
    fun refresh() { mutable.value.markerId?.let { lookup(it) } }
    fun move(delta: Int) { mutable.value = mutable.value.move(delta) }
    fun more() {
        val before = mutable.value; val obj = before.physicalObject ?: return
        if (before.loading) return
        request?.cancel(); val current = ++revision
        mutable.value = before.copy(loading = true, annotations = emptyList(), index = 0, lookupTiming = null)
        request = scope.launch {
            try {
                // Revalidate already loaded pages too: membership may have been revoked since the last request.
                val fresh = mutableListOf<Annotation>()
                do {
                    val page = repository.annotations(obj.id, fresh.size)
                    fresh.addAll(page)
                    if (page.size < 100) break
                } while (fresh.size < before.annotations.size + 100)
                if (current == revision) mutable.value = before.copy(annotations = fresh, index = 0, lookupTiming = null,
                    message = "${fresh.size} authorized notes")
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { if (current == revision) mutable.value = AnnotationState(markerId = before.markerId, message = e.message ?: "Refresh failed") }
        }
    }
    fun clear(message: String = "Ready to scan") { ++revision; request?.cancel(); gate.reset(); mutable.value = AnnotationState(message = message) }
}
