package org.spatial.annotations

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.Handler
import android.os.HandlerThread
import androidx.core.content.ContextCompat

/** Camera2 Y-plane capture, deliberately independent of a preview surface and Mercury SDK. */
class Camera2Capture(private val context: Context) : CameraCapture {
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
                val size = sizes.minByOrNull { kotlin.math.abs(it.width * it.height - 640 * 480) }!!
                val output = ImageReader.newInstance(size.width, size.height, ImageFormat.YUV_420_888, 2)
                run.reader = output
                var lastFrame = 0L
                output.setOnImageAvailableListener({ source ->
                    val image = source.acquireLatestImage() ?: return@setOnImageAvailableListener
                    try {
                        if (current != generation || image.timestamp - lastFrame < 250_000_000) return@setOnImageAvailableListener
                        lastFrame = image.timestamp
                        val plane = image.planes[0]; val buffer = plane.buffer; val origin = buffer.position()
                        val packed = ByteArray(image.width * image.height)
                        for (y in 0 until image.height) for (x in 0 until image.width) packed[y * image.width + x] = buffer.get(origin + y * plane.rowStride + x * plane.pixelStride)
                        onFrame(CameraFrame(packed, image.width, image.height, image.timestamp))
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
