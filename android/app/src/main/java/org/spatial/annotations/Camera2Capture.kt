package org.spatial.annotations

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.SystemClock
import android.os.Handler
import android.os.HandlerThread
import androidx.core.content.ContextCompat

/** Camera2 Y-plane capture, deliberately independent of a preview surface and Mercury SDK. */
class Camera2Capture(private val context: Context, private val color: Boolean = false, private val displayDegrees: () -> Int = { 0 }) : CameraCapture {
    private class CaptureRun(val worker: HandlerThread) {
        var device: CameraDevice? = null
        var session: CameraCaptureSession? = null
        var reader: ImageReader? = null
        var opening = false
    }
    private var running: CaptureRun? = null
    @Volatile private var generation = 0
    override fun start(onFrame: (CameraFrame) -> Unit, onStatus: (String) -> Unit) {
        stop()
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            onStatus("Camera permission required"); return
        }
        val current = ++generation
        val displayRotation = displayDegrees()
        val worker = HandlerThread("qr-camera").apply { start() }
        val run = CaptureRun(worker); running = run
        val handler = Handler(worker.looper)
        handler.post {
            if (current != generation) return@post
            try {
                val manager = context.getSystemService(Context.CAMERA_SERVICE) as CameraManager
                val candidates = manager.cameraIdList.filter { id ->
                    manager.getCameraCharacteristics(id).get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)?.getOutputSizes(ImageFormat.YUV_420_888)?.isNotEmpty() == true
                }
                val id = candidates.firstOrNull { manager.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK }
                    ?: candidates.firstOrNull() ?: error("No YUV camera available; use explicit simulation mode")
                val sizes = manager.getCameraCharacteristics(id).get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)!!.getOutputSizes(ImageFormat.YUV_420_888)
                val characteristics = manager.getCameraCharacteristics(id)
                val rotation = FrameGeometry.bufferRotation(characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION) ?: 0,
                    displayRotation, characteristics.get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_FRONT)
                val targetArea = if (color) 640 * 480 else 1280 * 960
                val size = (sizes.filter { it.width <= 1920 && it.height <= 1920 }.ifEmpty { sizes.toList() }).minByOrNull { kotlin.math.abs(it.width * it.height - targetArea) }!!
                val output = ImageReader.newInstance(size.width, size.height, ImageFormat.YUV_420_888, 2)
                run.reader = output
                var lastFrame = 0L
                output.setOnImageAvailableListener({ source ->
                    val image = source.acquireLatestImage() ?: return@setOnImageAvailableListener
                    try {
                        val receivedAt = SystemClock.elapsedRealtimeNanos()
                        if (current != generation || receivedAt - lastFrame < 250_000_000) return@setOnImageAvailableListener
                        lastFrame = receivedAt
                        val plane = image.planes[0]
                        val packed = YPlanePacking.copy(plane.buffer, image.width, image.height, plane.rowStride, plane.pixelStride)
                        fun chroma(index: Int): ByteArray? = if (!color) null else image.planes[index].let {
                            YPlanePacking.copy(it.buffer, (image.width + 1) / 2, (image.height + 1) / 2, it.rowStride, it.pixelStride)
                        }
                        onFrame(CameraFrame(packed, image.width, image.height, image.timestamp, rotation, chroma(1), chroma(2)))
                    } catch (_: Exception) { onStatus("Camera frame unavailable") } finally { image.close() }
                }, handler)
                run.opening = true
                manager.openCamera(id, object : CameraDevice.StateCallback() {
                    override fun onOpened(camera: CameraDevice) {
                        run.opening = false
                        if (current != generation) { camera.close(); worker.quitSafely(); return }
                        run.device = camera
                        try {
                            @Suppress("DEPRECATION")
                            camera.createCaptureSession(listOf(output.surface), object : CameraCaptureSession.StateCallback() {
                                override fun onConfigured(capture: CameraCaptureSession) {
                                    if (current != generation) { capture.close(); return }
                                    run.session = capture
                                    try {
                                        val request = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
                                            addTarget(output.surface)
                                            set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)
                                            val focusModes = characteristics.get(CameraCharacteristics.CONTROL_AF_AVAILABLE_MODES)
                                            if (focusModes?.contains(CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE) == true) {
                                                set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                                            }
                                        }
                                        capture.setRepeatingRequest(request.build(), null, handler)
                                        onStatus("Scanning QR · camera $id · ${size.width}×${size.height}")
                                    } catch (_: Exception) { onStatus("Camera stream failed; stop and retry") }
                                }
                                override fun onConfigureFailed(capture: CameraCaptureSession) { capture.close(); onStatus("Camera configuration unsupported") }
                            }, handler)
                        } catch (_: Exception) { onStatus("Cannot configure camera; stop and retry") }
                    }
                    override fun onDisconnected(camera: CameraDevice) { run.opening = false; camera.close(); if (current != generation) worker.quitSafely() else onStatus("Camera disconnected") }
                    override fun onError(camera: CameraDevice, error: Int) { run.opening = false; camera.close(); if (current != generation) worker.quitSafely() else onStatus("Camera error $error; close other camera apps and retry") }
                }, handler)
            } catch (e: Exception) { run.opening = false; if (current != generation) worker.quitSafely() else onStatus("Camera unavailable: ${e.message}") }
        }
    }
    override fun stop() {
        ++generation
        val run = running ?: return; running = null
        val worker = run.worker
        // Serialize close behind camera callbacks, avoiding ImageReader buffer races.
        Handler(worker.looper).post { run.session?.close(); run.session = null; run.device?.close(); run.device = null; run.reader?.close(); run.reader = null; if (!run.opening) worker.quitSafely() }
    }
}
