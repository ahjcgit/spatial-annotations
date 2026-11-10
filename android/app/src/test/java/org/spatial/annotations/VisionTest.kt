package org.spatial.annotations

import kotlinx.coroutines.*
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class VisionTest {
    @Test fun boundsRejectIncompleteInvalidAndInvertedBoxes() {
        assertTrue(Detection("cup", .6f, listOf(.1f,.2f,.8f,.9f)).valid())
        for (box in listOf(listOf(0f,1f),listOf(-1f,0f,1f,1f),listOf(.8f,0f,.2f,1f),listOf(Float.NaN,0f,1f,1f)))
            assertFalse(Detection("cup",.6f,box).valid())
    }
    @Test fun uploadsRawImageThenRetrievesCandidatesWithoutChoosingIdentity() = runBlocking {
        MockWebServer().use { server ->
            val auth=AuthState(MemoryTokens())
            auth.save(LoginResponse("session","2999-01-01T00:00:00Z",User("u","alice")))
            val api=ApiClient(server.url("/").toString().trimEnd('/'),auth)
            server.enqueue(MockResponse().setBody("""{"model":"NanoDet","width":600,"height":400,"inference_ms":110.5,"detections":[{"label":"cup","confidence":0.6,"box":[0.1,0.2,0.8,0.9]}]}"""))
            val bytes=byteArrayOf(1,2,3,4)
            val result=api.detect(bytes)
            assertEquals("cup",result.detections.single().label);assertTrue(result.detections.single().valid())
            val request=server.takeRequest()
            assertEquals("POST",request.method);assertEquals("/vision/detect",request.path)
            assertEquals("image/jpeg",request.getHeader("Content-Type"));assertEquals("Bearer session",request.getHeader("Authorization"))
            assertArrayEquals(bytes,request.body.readByteArray())
            server.enqueue(MockResponse().setBody("""[{"id":"a","marker_id":"ma","name":"Mug A"},{"id":"b","marker_id":"mb","name":"Mug B"}]"""))
            assertEquals(2,api.candidates("cup").size)
            assertEquals("/vision/candidates?label=cup",server.takeRequest().path)
            assertEquals(2,server.requestCount) // No implicit object or note lookup.
        }
    }
    @Test fun modelLookupNeverReportsQrRecognitionTime() {
        val row=ScanTelemetry("test","model_confirmed_lookup",100).finish(200,LookupTiming(110,190),3)!!
        assertNull(row["recognition_success"]);assertNull(row["recognition_latency_ms"])
        assertEquals(80L,row["backend_latency_ms"])
    }
}
