package org.spatial.annotations

import android.Manifest
import android.content.Intent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.google.gson.Gson
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicBoolean

/** Debug-only direct camera -> host review -> head-locked label measurement. */
class CodexProbeActivity : AppCompatActivity() {
    private val gson = Gson()
    private val handler = Handler(Looper.getMainLooper())
    private val camera by lazy { Camera2Capture(this, color = true) { 0 } }
    private lateinit var overlay: ProbeOverlay
    private var requestId = ""
    private var sourceHash = ""
    private var capturedNs = 0L
    private var generation = 0
    private var labels = emptyList<ProbeLabel>()
    private var state = linkedMapOf<String, Any?>()
    private var phase = "idle"
    private val controls = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) { intent?.let { command(it) } }
    }
    private fun now() = SystemClock.elapsedRealtimeNanos()
    private fun save() {
        state["requestId"] = requestId
        state["phase"] = phase
        val temp = File(filesDir, "codex-probe-status.tmp")
        temp.writeText(gson.toJson(state))
        check(temp.renameTo(File(filesDir, "codex-probe-status.json")))
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        overlay = ProbeOverlay(); setContentView(overlay)
        ContextCompat.registerReceiver(this, controls, IntentFilter("org.spatial.annotations.CODEX_PROBE_COMMAND"), ContextCompat.RECEIVER_EXPORTED)
        handler.post { command(intent) }
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent); setIntent(intent); command(intent)
    }
    private fun command(intent: Intent) {
        when (intent.getStringExtra("command")) {
            "capture" -> capture(intent.getStringExtra("request_id") ?: "")
            "apply" -> applyResponse()
            "clear" -> { generation++; camera.stop(); labels = emptyList(); phase = "cleared"; state["clearedNs"] = now(); save(); overlay.invalidate() }
        }
    }
    private fun capture(id: String) {
        if (!id.matches(Regex("[a-zA-Z0-9_-]{1,80}"))) return
        generation++; val current = generation
        camera.stop(); labels = emptyList(); sourceHash = ""; capturedNs = 0
        requestId = id; phase = "capturing"
        state = linkedMapOf("captureCommandReceivedNs" to now(), "clock" to "android_elapsed_realtime_ns", "displayKind" to "head_locked_snapshot_labels")
        save(); overlay.invalidate()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            phase = "error"; state["error"] = "camera_permission_required"; save(); overlay.invalidate(); return
        }
        val accepted = AtomicBoolean(false)
        // Skip initial frames for auto exposure; account for this warmup in capture timing.
        val warmupUntil = now() + 600_000_000L
        state["cameraWarmupMs"] = 600
        camera.start({ frame ->
            if (now() < warmupUntil || !accepted.compareAndSet(false, true)) return@start
            val callbackNs = now()
            try {
                val bitmap = FramePreview.bitmap(frame, true)
                val width = bitmap.width; val height = bitmap.height
                val bytes = java.io.ByteArrayOutputStream().use { bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 90, it); it.toByteArray() }
                bitmap.recycle()
                val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
                File(filesDir, "codex-probe-frame.jpg").writeBytes(bytes)
                val savedNs = now()
                runOnUiThread {
                    if (current != generation) return@runOnUiThread
                    camera.stop(); capturedNs = callbackNs; sourceHash = hash; phase = "captured"
                    state.putAll(mapOf("frameCallbackReceivedNs" to callbackNs, "sourceSensorTimestampNs" to frame.timestampNanos,
                        "frameSavedNs" to savedNs, "sourceSha256" to hash, "imageWidth" to width, "imageHeight" to height, "jpegBytes" to bytes.size))
                    save(); overlay.invalidate()
                }
            } catch (_: Exception) {
                runOnUiThread { if (current == generation) { camera.stop(); phase = "error"; state["error"] = "capture_failed"; save(); overlay.invalidate() } }
            }
        }, { message ->
            runOnUiThread {
                if (current == generation && phase == "capturing") {
                    state["cameraStatus"] = message
                    if (!message.startsWith("Scanning")) { phase = "error"; state["error"] = message; camera.stop() }
                    save(); overlay.invalidate()
                }
            }
        })
        handler.postDelayed({
            if (current == generation && phase == "capturing") { camera.stop(); phase = "error"; state["error"] = "capture_timeout"; save(); overlay.invalidate() }
        }, 15_000)
    }
    private fun applyResponse() {
        val received = now()
        try {
            require(phase == "captured") { "not_awaiting_response" }
            val response = gson.fromJson(File(filesDir, "codex-probe-input.json").readText(), ProbeResponse::class.java)
            CodexProbeProtocol.validate(response, requestId, sourceHash, received - capturedNs)
            labels = response.labels; phase = "displaying"
            state["applyReceivedNs"] = received
            state["labels"] = labels
            state["sourceAgeAtApplyMs"] = (received - capturedNs) / 1e6
            state["frameCommitCallbackSupported"] = Build.VERSION.SDK_INT >= 29 && overlay.isHardwareAccelerated
            val current = generation
            if (Build.VERSION.SDK_INT >= 29 && overlay.isHardwareAccelerated) {
                overlay.viewTreeObserver.registerFrameCommitCallback {
                    val committed = now()
                    handler.post {
                        if (current == generation && phase == "displaying") {
                            state["frameCommittedNs"] = committed
                            // GPU submission/commit callback, not measured optical presentation.
                            state["commitMeaning"] = "Android frame commit callback; not photon/optical visibility"
                            save()
                        }
                    }
                }
            }
            state["applyValidatedNs"] = now(); save(); overlay.invalidate()
            handler.postDelayed({
                if (current == generation && phase == "displaying") {
                    labels = emptyList(); phase = "expired"; state["labelsClearedNs"] = now(); save(); overlay.invalidate()
                }
            }, CodexProbeProtocol.DISPLAY_DURATION_MS)
        } catch (e: Exception) {
            labels = emptyList(); phase = "rejected"; state["rejectedNs"] = received
            state["error"] = e.message?.take(120) ?: "invalid_response"; save(); overlay.invalidate()
        }
    }
    override fun onPause() {
        generation++; camera.stop(); labels = emptyList()
        phase = "paused"; state["pausedNs"] = now(); save()
        super.onPause()
    }
    override fun onDestroy() { unregisterReceiver(controls); handler.removeCallbacksAndMessages(null); camera.stop(); super.onDestroy() }
    private inner class ProbeOverlay : View(this) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(canvas: Canvas) {
            val start = now()
            canvas.drawColor(Color.BLACK)
            val eyeWidth = width / 2f
            repeat(2) { eye ->
                canvas.save(); canvas.clipRect(eye * eyeWidth, 0f, (eye + 1) * eyeWidth, height.toFloat()); canvas.translate(eye * eyeWidth, 0f)
                paint.textAlign = Paint.Align.CENTER; paint.color = Color.WHITE; paint.textSize = 23f
                canvas.drawText("CODEX · CAPTURED IMAGE", eyeWidth / 2, 52f, paint)
                paint.textSize = 18f; paint.color = Color.LTGRAY
                val status = if (phase == "displaying") "Image age at receipt: %.1f s".format((state["sourceAgeAtApplyMs"] as? Double ?: 0.0) / 1000) else phase.uppercase()
                canvas.drawText(status, eyeWidth / 2, 86f, paint)
                if (phase == "displaying") {
                    labels.forEachIndexed { i, item ->
                        paint.color = if (item.uncertain) Color.YELLOW else if (item.identity == "A") Color.rgb(100,235,235) else Color.rgb(255,175,95)
                        paint.textSize = 42f
                        val text = "${item.identity}${if (item.uncertain) " ?" else ""} · ${item.label}"
                        while (paint.measureText(text) > eyeWidth - 28 && paint.textSize > 26f) paint.textSize -= 1f
                        canvas.drawText(text, eyeWidth / 2, 170f + i * 120f, paint)
                        paint.textSize = 22f; paint.color = Color.WHITE
                        canvas.drawText("${item.side.uppercase()} in captured image", eyeWidth / 2, 205f + i * 120f, paint)
                    }
                    if (labels.isEmpty()) { paint.textSize = 30f; canvas.drawText("No supported bottle labels", eyeWidth / 2, 200f, paint) }
                    paint.color = Color.LTGRAY; paint.textSize = 17f
                    canvas.drawText("Fixed list · not object-aligned · 30 s", eyeWidth / 2, height - 25f, paint)
                }
                canvas.restore()
            }
            if (phase == "displaying" && !state.containsKey("firstDrawStartNs")) {
                state["firstDrawStartNs"] = start; state["firstDrawEndNs"] = now()
                state["hardwareAccelerated"] = isHardwareAccelerated
                val current = generation
                handler.post { if (current == generation) save() }
            }
        }
    }
}
