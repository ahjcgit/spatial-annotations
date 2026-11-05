package org.spatial.annotations

import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class MemoryTokens : TokenStore { var value: String? = null; override fun read() = value; override fun write(value: String?) { this.value = value } }
private const val MARKER = "e3ef16ee-5c85-416e-a4e3-c0fdb6477371"
private val note = Annotation("n", "o", "Private text", "u", "alice", "2026-01-01T00:00:00Z", "private")

@OptIn(ExperimentalCoroutinesApi::class)
class CoreTest {
    @Test fun markerProtocolIsStrict() {
        assertEquals(MARKER, MarkerId.parse("spatial:v1:$MARKER"))
        assertEquals(MARKER, MarkerId.parse(MARKER.uppercase()))
        assertNull(MarkerId.parse("spatial:v2:$MARKER"))
        assertNull(MarkerId.parse("https://untrusted.example/$MARKER"))
        assertNull(MarkerId.parse("1-1-1-1-1"))
        assertNull(MarkerId.parse("$MARKER/../secret"))
    }
    @Test fun realQrDecodingAndBlankFrame() {
        val matrix = QRCodeWriter().encode(MarkerId.payload(MARKER), BarcodeFormat.QR_CODE, 480, 480)
        val data = ByteArray(480 * 480) { i -> if (matrix[i % 480, i / 480]) 0 else 255.toByte() }
        val recognizer = QrObjectRecognizer()
        assertEquals(MARKER, recognizer.recognize(CameraFrame(data, 480, 480, 1))?.markerId)
        assertNull(recognizer.recognize(CameraFrame(ByteArray(640 * 480) { 255.toByte() }, 640, 480, 2)))
    }
    @Test fun unrelatedQrDoesNotBecomeAnObject() {
        val matrix = QRCodeWriter().encode("https://example.org", BarcodeFormat.QR_CODE, 300, 300)
        val data = ByteArray(300 * 300) { i -> if (matrix[i % 300, i / 300]) 0 else 255.toByte() }
        assertNull(QrObjectRecognizer().recognize(CameraFrame(data, 300, 300, 1)))
    }
    @Test fun authenticationPersistsAndExpires() {
        val store = MemoryTokens(); val clock = { Instant.parse("2026-01-01T00:00:00Z") }
        val state = AuthState(store, clock)
        assertNull(state.token())
        state.save(LoginResponse("token", "2026-01-02T00:00:00Z", User("u", "alice")))
        assertEquals("token", AuthState(store, clock).token())
        assertNull(AuthState(store) { Instant.parse("2026-01-02T00:00:00Z") }.token())
        assertNull(store.value)
        store.value = "corrupt"; assertNull(AuthState(store, clock).token())
    }
    @Test fun logoutClearsStoredCredentials() {
        val store = MemoryTokens(); val auth = AuthState(store)
        auth.save(LoginResponse("secret", "2999-01-01T00:00:00Z", User("u", "alice")))
        auth.clear(); assertNull(auth.session); assertNull(store.value)
    }
    @Test fun cameraPermissionDecision() {
        assertEquals(CameraPermissionPolicy.Action.START_CAMERA, CameraPermissionPolicy.action(true, true, false))
        assertEquals(CameraPermissionPolicy.Action.REQUEST_PERMISSION, CameraPermissionPolicy.action(false, false, false))
        assertEquals(CameraPermissionPolicy.Action.REQUEST_PERMISSION, CameraPermissionPolicy.action(false, true, true))
        assertEquals(CameraPermissionPolicy.Action.SHOW_SETTINGS, CameraPermissionPolicy.action(false, true, false))
    }
    @Test fun lookupGateThrottlesFrames() {
        val gate = LookupGate()
        assertTrue(gate.accept(MARKER, 0)); assertFalse(gate.accept(MARKER, 50)); assertTrue(gate.accept(MARKER, 10_001))
        assertTrue(gate.accept("different", 10_002)); gate.reset(); assertTrue(gate.accept("different", 10_003))
    }
    @Test fun annotationNavigationWrapsAndHandlesEmpty() {
        assertEquals(0, AnnotationState().move(-1).index)
        val state = AnnotationState(annotations = listOf(note, note.copy(id = "n2")))
        assertEquals("n2", state.move(-1).selected?.id)
        assertEquals("n", state.move(2).selected?.id)
    }
    @Test fun serverPolicyRejectsPublicHttpCredentialsAndPaths() {
        assertEquals("http://192.168.1.76:8000", ServerAddress.normalize("http://192.168.1.76:8000/", true))
        assertEquals("https://notes.example.org", ServerAddress.normalize("https://notes.example.org", false))
        assertEquals("http://127.0.0.1:8000", ServerAddress.normalize("http://127.0.0.1:8000/", true))
        assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize("http://127.0.0.1:8000", false) }
        for (url in listOf("http://example.org", "http://8.8.8.8", "https://user:secret@example.org", "https://example.org/path", "https://example.org?token=x")) {
            assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize(url, true) }
        }
        assertThrows(IllegalArgumentException::class.java) { ServerAddress.normalize("http://192.168.1.76", false) }
    }
    @Test fun lookupStateUnknownAndAuthorizationFailureClearNotes() = runTest {
        var failure: Exception? = null
        val repository = object : AnnotationRepository {
            override suspend fun lookup(marker: String): PhysicalObject { failure?.let { throw it }; return PhysicalObject("o", marker, "Mug") }
            override suspend fun annotations(objectId: String, offset: Int) = listOf(note)
        }
        val controller = ScanController(repository, this)
        controller.lookup(MARKER); advanceUntilIdle(); assertEquals("Mug", controller.state.value.physicalObject?.name); assertEquals(note, controller.state.value.selected)
        failure = ApiException(401, "Session expired")
        controller.refresh(); assertTrue(controller.state.value.annotations.isEmpty()); advanceUntilIdle()
        assertTrue(controller.state.value.annotations.isEmpty()); assertFalse(controller.state.value.unknown)
        failure = ApiException(404, "Unknown")
        controller.lookup(MARKER); advanceUntilIdle(); assertTrue(controller.state.value.unknown)
    }
    @Test fun oldResponseCannotOverwriteNewObjectOrLogout() = runTest {
        val repository = object : AnnotationRepository {
            override suspend fun lookup(marker: String): PhysicalObject { delay(100); return PhysicalObject(marker, marker, "Mug") }
            override suspend fun annotations(objectId: String, offset: Int) = listOf(note.copy(objectId = objectId))
        }
        val controller = ScanController(repository, this)
        controller.lookup(MARKER); runCurrent(); controller.clear("Signed out"); advanceUntilIdle()
        assertTrue(controller.state.value.annotations.isEmpty()); assertEquals("Signed out", controller.state.value.message)
        controller.lookup(MARKER); runCurrent(); controller.lookup("invalid"); advanceUntilIdle()
        assertEquals("Invalid marker ID", controller.state.value.message); assertNull(controller.state.value.physicalObject)
        val second = "11111111-1111-4111-8111-111111111111"
        controller.lookup(MARKER); runCurrent(); controller.lookup(second); advanceUntilIdle()
        assertEquals(second, controller.state.value.physicalObject?.id)
    }
}
