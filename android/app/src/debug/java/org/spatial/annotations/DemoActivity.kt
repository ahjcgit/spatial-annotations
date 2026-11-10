package org.spatial.annotations

import android.Manifest
import android.content.Intent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.graphics.*
import android.os.Bundle
import android.os.SystemClock
import android.util.Base64
import android.view.View
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.gson.Gson
import com.google.gson.JsonParser
import kotlinx.coroutines.*
import java.io.File
import java.util.concurrent.atomic.AtomicBoolean

/** Debug-only live presentation; account setup remains in app-private storage. */
class DemoActivity : AppCompatActivity() {
    private lateinit var overlay: Overlay
    private val camera by lazy { Camera2Capture(this, color = true) { 0 } }
    private var job: Job? = null
    private var processing: Job? = null
    private var watchdog: Job? = null
    @Volatile private var generation = 0
    private var running = false
    private var userIndex = 0
    private var objectIndex = 0
    private var mode = "fallback"
    private var offsetX = 0f
    private var offsetY = 0f
    private var scale = 1f
    private var disparity = 0f
    private var lastResult = 0L
    private var frameNumber = 0L
    private var state = linkedMapOf<String, Any?>()
    private val config by lazy { JsonParser.parseString(File(filesDir, "demo-config.json").readText()).asJsonObject }
    private val target get() = config.get("target")?.asString ?: "bottle"
    private var checks = emptyMap<String, Boolean>()
    private val controls = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) { intent?.let { handleCommand(it) } }
    }
    private var currentDetection: Detection? = null
    private var label = ""
    private var labelVisibility = ""
    private fun publish(phase: String, message: String) {
        state["phase"] = phase; state["message"] = message
        state["user"] = if (userIndex == 0) "Alice" else "Bob"
        state["mode"] = mode
        state["alignment"] = mapOf("x" to offsetX, "y" to offsetY, "scale" to scale, "disparity" to disparity)
        state["label"] = label; state["labelVisibility"] = labelVisibility
        state["checks"] = checks
        File(filesDir, "demo-result.tmp").apply { writeText(Gson().toJson(state)); renameTo(File(filesDir, "demo-result.json")) }
        overlay.invalidate()
    }
    private fun clearLabels() {
        label = ""; labelVisibility = ""; currentDetection = null
        state.remove("notes"); state.remove("selectedObject"); state["detections"] = emptyList<Detection>()
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        @Suppress("DEPRECATION")
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        overlay = Overlay(); setContentView(overlay)
        ContextCompat.registerReceiver(this, controls, IntentFilter("org.spatial.annotations.DEMO_COMMAND"), ContextCompat.RECEIVER_EXPORTED)
    }
    override fun onResume() { super.onResume(); if (!running) startLive() }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent); setIntent(intent)
        handleCommand(intent)
    }
    private fun handleCommand(intent: Intent) {
        when (intent.getStringExtra("command")) {
            "run" -> startLive()
            "stop" -> { stopLive(); clearLabels(); publish("stopped", "Live camera stopped") }
            "alice" -> { userIndex = 0; startLive() }
            "bob" -> { userIndex = 1; startLive() }
            "mug-a" -> { objectIndex = 0; startLive() }
            "mug-b" -> { objectIndex = 1; startLive() }
            "fallback" -> { mode = "fallback"; publish(state["phase"].toString(), state["message"].toString()) }
            "optical" -> { mode = "optical"; publish(state["phase"].toString(), state["message"].toString()) }
            "left" -> { offsetX -= 12f; redraw() }
            "right" -> { offsetX += 12f; redraw() }
            "up" -> { offsetY -= 12f; redraw() }
            "down" -> { offsetY += 12f; redraw() }
            "larger" -> { scale = (scale + .1f).coerceAtMost(3f); redraw() }
            "smaller" -> { scale = (scale - .1f).coerceAtLeast(.3f); redraw() }
            "eyes-in" -> { disparity -= 4f; redraw() }
            "eyes-out" -> { disparity += 4f; redraw() }
            "reset" -> { offsetX = 0f; offsetY = 0f; scale = 1f; disparity = 0f; redraw() }
        }
    }
    private fun redraw() { publish(state["phase"].toString(), state["message"].toString()) }
    private fun stopLive() {
        running = false; ++generation; camera.stop(); job?.cancel(); processing?.cancel(); watchdog?.cancel()
    }
    private suspend fun clientFor(index: Int): ApiClient {
        val auth = AuthState(object : TokenStore { override fun read(): String? = null; override fun write(value: String?) {} })
        val client = ApiClient(ServerAddress.normalize(config["backend"].asString, true), auth)
        val user = config["users"].asJsonArray[index].asJsonObject
        auth.save(client.login(user["username"].asString, user["password"].asString))
        return client
    }
    private fun startLive() {
        stopLive(); running = true
        val run = generation
        clearLabels()
        state = linkedMapOf("runId" to java.util.UUID.randomUUID().toString(), "target" to target, "frameId" to 0, "color" to true)
        publish("connecting", "Connecting ${if (userIndex == 0) "Alice" else "Bob"}…")
        job = lifecycleScope.launch {
            try {
                val objects = config["objects"].asJsonArray
                if (checks.isEmpty()) {
                    val a = clientFor(0); val b = clientFor(1)
                    try {
                        val first = a.lookup(objects[0].asJsonObject["marker_id"].asString)
                        val second = a.lookup(objects[1].asJsonObject["marker_id"].asString)
                        val alice = a.annotations(first.id); val bob = b.annotations(first.id)
                        checks = mapOf("connection" to true, "objectIsolation" to (first.id != second.id && a.annotations(second.id).isEmpty()),
                            "privacy" to (alice.any { it.visibility == "private" } && bob.none { it.visibility == "private" }))
                    } finally { a.logout(); b.logout() }
                }
                val client = clientFor(userIndex)
                if (run != generation) return@launch
                if (ContextCompat.checkSelfPermission(this@DemoActivity, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
                    requestPermissions(arrayOf(Manifest.permission.CAMERA), 41); publish("permission", "Allow camera to begin")
                } else capture(run, client)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { if (run == generation) { clearLabels(); publish("error", e.message ?: "Connection failed") } }
        }
    }
    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, grants: IntArray) {
        super.onRequestPermissionsResult(code, permissions, grants)
        if (code == 41 && grants.firstOrNull() == PackageManager.PERMISSION_GRANTED) startLive()
        else publish("error", "Camera permission is required")
    }
    private fun capture(run: Int, client: ApiClient) {
        val busy = AtomicBoolean(false)
        lastResult = SystemClock.elapsedRealtime()
        publish("capturing", "Live camera starting…")
        watchdog = lifecycleScope.launch {
            while (run == generation) {
                delay(500)
                if (SystemClock.elapsedRealtime() - lastResult > 3500) {
                    clearLabels(); publish("stalled", "Waiting for a fresh camera result…")
                }
            }
        }
        camera.start({ image ->
            if (run == generation && busy.compareAndSet(false, true)) {
                val started = SystemClock.elapsedRealtime()
                val bitmap = FramePreview.bitmap(image, true)
                runOnUiThread {
                    if (run != generation) { bitmap.recycle(); busy.set(false); return@runOnUiThread }
                    processing = lifecycleScope.launch {
                        try {
                            val bytes = withContext(Dispatchers.Default) {
                                java.io.ByteArrayOutputStream().use { bitmap.compress(Bitmap.CompressFormat.JPEG, 85, it); it.toByteArray() }
                            }
                            val result = client.detect(bytes)
                            if (run != generation) return@launch
                            val detections = result.detections.filter { it.valid() }
                            val targets = detections.filter { it.label == target }
                            clearLabels()
                            val notes = if (targets.size == 1) client.annotations(config["objects"].asJsonArray[objectIndex].asJsonObject["id"].asString) else emptyList()
                            if (run != generation) return@launch
                            if (targets.size == 1) {
                                currentDetection = targets[0]
                                val selected = notes.firstOrNull { it.visibility == "private" } ?: notes.firstOrNull { it.visibility == "group" } ?: notes.firstOrNull()
                                label = selected?.content ?: "No notes for this object"
                                labelVisibility = selected?.visibility ?: "public"
                                state["selectedObject"] = config["objects"].asJsonArray[objectIndex].asJsonObject["name"].asString
                            }
                            state["notes"] = notes
                            state["detections"] = detections
                            state["image"] = "data:image/jpeg;base64," + Base64.encodeToString(bytes, Base64.NO_WRAP)
                            state["imageWidth"] = bitmap.width; state["imageHeight"] = bitmap.height
                            state["sourceFrameTimestampNs"] = image.timestampNanos
                            state["acceptedAtElapsedMs"] = started
                            state["resultAtElapsedMs"] = SystemClock.elapsedRealtime()
                            state["model"] = result.model
                            state["inferenceMs"] = result.inferenceMs
                            state["pipelineMs"] = SystemClock.elapsedRealtime() - started
                            state["frameId"] = ++frameNumber
                            lastResult = SystemClock.elapsedRealtime()
                            publish(if (targets.size == 1) "live" else "no_match", when {
                                targets.size > 1 -> "Several bottles visible. Show only the selected sanitizer."
                                targets.size == 1 -> "Live · ${if (userIndex == 0) "Alice" else "Bob"} · ${notes.size} permitted notes"
                                else -> "Aim at the sanitizer bottle"
                            })
                        } catch (e: CancellationException) { throw e }
                        catch (e: Exception) { if (run == generation) { clearLabels(); publish("error", e.message ?: "Detection failed") } }
                        finally { bitmap.recycle(); busy.set(false) }
                    }
                }
            }
        }, { status -> runOnUiThread {
            if (run == generation && !status.startsWith("Scanning")) { clearLabels(); publish("error", status) }
        } })
    }
    override fun onDestroy() { unregisterReceiver(controls); super.onDestroy() }
    override fun onPause() { stopLive(); clearLabels(); publish("stopped", "Camera paused"); super.onPause() }

    /** Black is unlit on the optical display: render labels only, no Android panels or camera image. */
    private inner class Overlay : View(this) {
        private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        override fun onDraw(canvas: Canvas) {
            canvas.drawColor(Color.BLACK)
            val eyeWidth = width / 2f
            repeat(2) { eye ->
                canvas.save(); canvas.clipRect(eye * eyeWidth, 0f, (eye + 1) * eyeWidth, height.toFloat())
                canvas.translate(eye * eyeWidth, 0f)
                paint.color = if (userIndex == 0) Color.rgb(178,245,204) else Color.rgb(163,210,255)
                paint.textSize = 16f; paint.textAlign = Paint.Align.CENTER
                canvas.drawText("${if (userIndex == 0) "ALICE" else "BOB"} · ${if (mode == "optical") "ALIGN OVERLAY" else "LIVE LABEL"}", eyeWidth / 2, 38f, paint)
                val detection = currentDetection
                if (label.isNotBlank() && detection != null) {
                    var x = eyeWidth / 2; var y = height - 120f
                    if (mode == "optical") {
                        val b = detection.box
                        x = (eyeWidth / 2 + ((b[0] + b[2]) / 2 - .5f) * eyeWidth * scale + offsetX + if (eye == 0) disparity else -disparity).coerceIn(175f, eyeWidth - 175f)
                        y = (height / 2 + (b[1] - .5f) * height * scale + offsetY).coerceIn(95f, height - 120f)
                        paint.style = Paint.Style.STROKE; paint.strokeWidth = 2f
                        canvas.drawCircle(x, y + 35f, 8f, paint); paint.style = Paint.Style.FILL
                        canvas.drawLine(x, y + 25f, x, y + 12f, paint)
                    }
                    paint.textSize = 14f
                    canvas.drawText(labelVisibility.uppercase(), x, y - 48f, paint)
                    paint.textSize = 21f
                    val lines = mutableListOf<String>(); var line = ""
                    for (word in label.split(' ')) {
                        val next = if (line.isBlank()) word else "$line $word"
                        if (paint.measureText(next) > 340f && line.isNotEmpty()) { lines += line; line = word } else line = next
                    }
                    lines += line
                    lines.take(3).forEachIndexed { i, value -> canvas.drawText(value, x, y - 18f + i * 25f, paint) }
                } else {
                    paint.textSize = 20f
                    canvas.drawText(if (running) "Looking for the sanitizer…" else "Live demo paused", eyeWidth / 2, height - 90f, paint)
                }
                canvas.restore()
            }
        }
    }
}
