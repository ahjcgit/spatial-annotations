package org.spatial.annotations

import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.*
import kotlinx.coroutines.test.*
import org.junit.Assert.*
import org.junit.Test

private const val A = "11111111-1111-4111-8111-111111111111"
private const val B = "22222222-2222-4222-8222-222222222222"
@OptIn(ExperimentalCoroutinesApi::class)
class VisualizationTest {
    @Test fun decodingRotatedNonSquareFramesKeepsFeatureCoordinatesInImageSpace() {
        for (id in listOf(A, B)) for (rotation in listOf(0, 90, 180, 270)) {
            val qr = QRCodeWriter().encode(MarkerId.payload(id), BarcodeFormat.QR_CODE, 300, 300)
            val width = 640; val height = 480
            val size = FrameGeometry.size(width, height, rotation)
            val pixels = ByteArray(width * height) { 255.toByte() }
            for (y in 0 until 300) for (x in 0 until 300) {
                val p = FrameGeometry.rotate(ImagePoint((x + 170).toFloat(), (y + 90).toFloat()), width, height, rotation)
                pixels[p.y.toInt() * size.width + p.x.toInt()] = if (qr[x, y]) 0 else 255.toByte()
            }
            val decoded = QrObjectRecognizer().recognize(CameraFrame(pixels, size.width, size.height, 0, rotation))!!
            assertEquals(id, decoded.markerId)
            assertTrue(decoded.points.size >= 3)
            for (point in decoded.points) {
                assertTrue(point.x in 0f..size.width.toFloat() && point.y in 0f..size.height.toFloat())
                assertEquals(0, pixels[point.y.toInt() * size.width + point.x.toInt()].toInt())
            }
        }
    }
    @Test fun rotationAndLetterboxTransformMatchKnownPixelCenters() {
        assertEquals(ImagePoint(479f, 0f), FrameGeometry.rotate(ImagePoint(0f, 0f), 640, 480, 90))
        assertEquals(ImagePoint(639f, 479f), FrameGeometry.rotate(ImagePoint(0f, 0f), 640, 480, 180))
        assertEquals(ImagePoint(0f, 639f), FrameGeometry.rotate(ImagePoint(0f, 0f), 640, 480, 270))
        val center = ImagePoint(319.5f, 239.5f)
        assertEquals(ImagePoint(500f, 150f), FrameGeometry.fit(center, ImageSize(640, 480), 1000, 300))
        for (angle in listOf(0,90,180,270)) {
            val p = FrameGeometry.rotate(ImagePoint(123f, 87f), 640, 480, angle)
            val size = FrameGeometry.size(640, 480, angle)
            assertEquals(ImagePoint(123f,87f), FrameGeometry.rotate(p, size.width, size.height, 360-angle))
        }
        assertEquals(0, FrameGeometry.bufferRotation(90, 270, false))
        assertEquals(90, FrameGeometry.bufferRotation(270, 0, true))
    }
    @Test fun missingPartialAndInvalidPointsNeverInventCorners() {
        assertTrue(FrameGeometry.validPoints(emptyList(), 640, 480).isEmpty())
        val point = ImagePoint(20f, 30f)
        assertEquals(listOf(point), FrameGeometry.validPoints(listOf(point, ImagePoint(Float.NaN,0f), ImagePoint(-1f,2f), ImagePoint(640f,1f)),640,480))
    }
    @Test fun opticalProtocolRejectsBareUuidAndMalformedFrames() {
        val qr = QRCodeWriter().encode(A, BarcodeFormat.QR_CODE, 300, 300)
        val pixels = ByteArray(90000) { if(qr[it%300,it/300]) 0 else 255.toByte() }
        assertNull(QrObjectRecognizer().recognize(CameraFrame(pixels,300,300,0)))
        assertNull(QrObjectRecognizer().recognize(CameraFrame(byteArrayOf(),640,480,0)))
        assertEquals("SIMULATION", SimulatedRecognizer(A).recognize(CameraFrame(byteArrayOf(),0,0,0))?.source)
    }
    @Test fun telemetrySeparatesOpticalSimulatedFailureAndUiBoundaries() {
        val trace = ScanTelemetry("unit", "camera_qr", 100)
        trace.marker = A; trace.detected = 300; trace.frames = 4
        val row = trace.finish(450, LookupTiming(310,430), 3)!!
        assertEquals(200L,row["recognition_latency_ms"]); assertEquals(120L,row["backend_latency_ms"])
        assertEquals(130L,row["detection_to_retrieval_ms"]); assertEquals(20L,row["retrieval_to_ui_ms"])
        assertEquals(350L,row["total_latency_ms"]); assertNull(trace.finish(460))
        val manual = ScanTelemetry("unit", "simulated_lookup", 100).finish(200, LookupTiming(110,190))!!
        assertNull(manual["recognition_latency_ms"]); assertNull(manual["recognition_success"])
        val failure = ScanTelemetry("unit", "camera_qr", 0).finish(15000, failure="recognition_timeout")!!
        assertEquals(false,failure["recognition_success"]); assertNull(failure["backend_success"])
    }
    @Test fun dpadUpDownRemainAvailableForNativeFocusNavigation() {
        assertNull(StandardDeviceInput().actionForKey(19)); assertNull(StandardDeviceInput().actionForKey(20))
        assertEquals(DeviceAction.NEXT,StandardDeviceInput().actionForKey(22))
    }
    @Test fun cancelledUncooperativeLookupCannotPublishAndNetworkRetryRecovers() = runTest {
        var fail = false
        val repo = object : AnnotationRepository {
            override suspend fun lookup(marker: String): PhysicalObject {
                if (marker == A) withContext(NonCancellable) { delay(100) }
                if (fail) throw java.io.IOException("Offline")
                return PhysicalObject(marker,marker,marker)
            }
            override suspend fun annotations(objectId: String, offset: Int) = emptyList<Annotation>()
        }
        val controller = ScanController(repo,this) { testScheduler.currentTime }
        controller.lookup(A); runCurrent(); controller.lookup(B); advanceUntilIdle()
        assertEquals(B,controller.state.value.physicalObject?.id)
        fail = true; controller.refresh(); assertTrue(controller.state.value.loading); advanceUntilIdle()
        assertNull(controller.state.value.physicalObject); assertEquals("network",controller.state.value.lookupTiming?.failure)
        fail = false; controller.refresh(); advanceUntilIdle(); assertEquals(B,controller.state.value.physicalObject?.id)
        controller.clear("Signed out"); assertTrue(controller.state.value.annotations.isEmpty()); assertNull(controller.state.value.markerId)
    }
    @Test fun loadingMoreRevalidatesPreviouslyVisiblePrivateOrGroupNotes() = runTest {
        var revoked = false
        val note = Annotation("n","o","group content","u","alice","2026-01-01","group")
        val repo = object : AnnotationRepository {
            override suspend fun lookup(marker: String) = PhysicalObject("o",marker,"Mug")
            override suspend fun annotations(objectId: String, offset: Int) = if (revoked) emptyList() else listOf(note)
        }
        val controller = ScanController(repo,this)
        controller.lookup(A);advanceUntilIdle();assertEquals(1,controller.state.value.annotations.size)
        revoked = true;controller.more();assertTrue(controller.state.value.annotations.isEmpty())
        advanceUntilIdle();assertTrue(controller.state.value.annotations.isEmpty())
    }

    @Test fun overlappingCameraWorkersCanShareDecoderDuringRapidRescan() {
        val decoder = QrObjectRecognizer()
        val frames = listOf(A,B).associateWith { id ->
            val qr = QRCodeWriter().encode(MarkerId.payload(id),BarcodeFormat.QR_CODE,300,300)
            CameraFrame(ByteArray(90000) { if(qr[it%300,it/300]) 0 else 255.toByte() },300,300,0)
        }
        val workers = java.util.concurrent.Executors.newFixedThreadPool(4)
        val start = java.util.concurrent.CountDownLatch(1)
        try {
            val results = (0 until 24).map { index ->
                val id = if(index%2==0) A else B
                workers.submit<Boolean> { start.await(); decoder.recognize(frames.getValue(id))?.markerId == id }
            }
            start.countDown()
            results.forEach { assertTrue(it.get(5,java.util.concurrent.TimeUnit.SECONDS)) }
        } finally { workers.shutdownNow() }
    }

}
