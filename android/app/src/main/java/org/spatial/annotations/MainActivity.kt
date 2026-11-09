package org.spatial.annotations

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import android.view.Surface
import com.google.gson.GsonBuilder
import java.util.concurrent.atomic.AtomicBoolean
import android.net.Uri
import android.os.Bundle
import android.os.SystemClock
import android.provider.Settings
import android.text.InputType
import android.view.KeyEvent
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.*

class MainActivity : AppCompatActivity(), AnnotationRenderer {
    private val prefs by lazy { getSharedPreferences("settings", MODE_PRIVATE) }
    private lateinit var auth: AuthState
    private var api: ApiClient? = null
    private var controller: ScanController? = null
    private var collector: Job? = null
    private var userOperation: Job? = null
    private val camera by lazy { Camera2Capture(this) {
        @Suppress("DEPRECATION")
        when (windowManager.defaultDisplay.rotation) { Surface.ROTATION_90 -> 90; Surface.ROTATION_180 -> 180; Surface.ROTATION_270 -> 270; else -> 0 }
    } }
    private val recognizer = QrObjectRecognizer()
    private val input = StandardDeviceInput()
    private lateinit var root: LinearLayout
    private lateinit var message: TextView
    private var title: TextView? = null
    private var card: TextView? = null
    private var scanStatus: TextView? = null
    private var preview: FramePreview? = null
    private var progress: ProgressBar? = null
    private var trace: ScanTelemetry? = null
    private var scanTimeout: Job? = null
    private fun now() = SystemClock.elapsedRealtimeNanos() / 1_000_000
    private fun beginTrace(method: String, marker: String? = null) {
        endTrace("superseded")
        trace = ScanTelemetry(if (Build.FINGERPRINT.contains("generic") || Build.MODEL.contains("sdk")) "android_emulator" else "android_device_unclassified", method, now()).also { it.marker = marker }
    }
    private fun endTrace(failure: String? = null, state: AnnotationState? = null) {
        trace?.finish(now(), state?.lookupTiming, state?.annotations?.size ?: 0, failure)?.let { Log.i("SpatialTelemetry", GsonBuilder().serializeNulls().create().toJson(it)) }
    }
    @Volatile private var scanGeneration = 0
    private var inScan = false
    @Volatile private var scanning = false
    private var simulated = false
    private var modelMode = false
    private var modelJob: Job? = null
    private var modelDialog: AlertDialog? = null
    private var savedMarker: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        auth = AuthState(SecureTokenStore(this))
        setupClient(prefs.getString("server", "") ?: "")
        settingsScreen()
    }
    private fun setupClient(server: String) {
        userOperation?.cancel(); collector?.cancel(); controller?.clear(); api = null; controller = null
        if (server.isBlank()) return
        try {
            val normalized = ServerAddress.normalize(server, BuildConfig.DEBUG)
            api = ApiClient(normalized, auth)
            controller = ScanController(NetworkAnnotationRepository(api!!), lifecycleScope, ::now)
            collector = lifecycleScope.launch { controller!!.state.collect { if (inScan) render(it) } }
        } catch (_: Exception) { /* Invalid saved settings remain editable in the settings screen. */ }
    }
    private fun baseScreen() {
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 20, 20, 30); setBackgroundColor(0xff000000.toInt()) }
        val scroll = ScrollView(this).apply { addView(root) }
        setContentView(scroll)
        message = label("")
    }
    private fun label(value: String, size: Float = 20f): TextView = TextView(this).apply {
        text = value; textSize = size; setTextColor(0xffedf4ec.toInt()); setPadding(0, 8, 0, 8); root.addView(this)
    }
    private fun field(hintText: String, value: String = "", password: Boolean = false): EditText = EditText(this).apply {
        hint = hintText; setText(value); textSize = 18f
        inputType = if (password) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD else InputType.TYPE_CLASS_TEXT
        root.addView(this)
    }
    private fun button(value: String, action: () -> Unit): Button = Button(this).apply {
        text = value; minHeight = (48 * resources.displayMetrics.density).toInt(); setOnClickListener { action() }; root.addView(this)
    }
    private fun launchTask(block: suspend () -> Unit) {
        userOperation?.cancel()
        userOperation = lifecycleScope.launch {
            try { block() }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (e is ApiException && e.code == 401) controller?.clear("Session expired. Open Settings and sign in again.")
                message.text = e.message ?: "Operation failed. Check the backend connection."
            }
        }
    }
    private fun settingsScreen() {
        stopCamera(); inScan = false; controller?.clear(); baseScreen()
        label("Spatial Notes", 30f)
        label("${DeviceIntegration.description}\nScreen-space panel · spatial tracking unavailable", 16f)
        val server = field("Backend URL, e.g. https://notes.example.org", prefs.getString("server", "") ?: "")
        label("Debug HTTP supports a private LAN IPv4 address or 127.0.0.1 through USB setup. Credentials use that connection.", 14f)
        fun saveServer(): Boolean = try {
            val normalized = ServerAddress.normalize(server.text.toString(), BuildConfig.DEBUG)
            if (normalized != prefs.getString("server", "")) { auth.clear(); prefs.edit().putString("server", normalized).apply() }
            setupClient(normalized); true
        } catch (e: Exception) { message.text = e.message; false }
        button("Save server") { if (saveServer()) { settingsScreen(); message.text = "Server saved. Sign in or browse public notes." } }
        label(auth.session?.takeIf { auth.token() != null }?.let { "Signed in: ${it.user.username}" } ?: "Guest · public notes only")
        val username = field("Username")
        val password = field("Password (at least 10 characters)", password = true)
        fun authenticate(register: Boolean) {
            if (!saveServer()) return
            val user = username.text.toString().trim(); val pass = password.text.toString()
            launchTask {
                auth.clear(); controller?.clear()
                if (register) api!!.register(user, pass)
                auth.save(api!!.login(user, pass)); password.text.clear(); settingsScreen(); message.text = "Signed in."
            }
        }
        button("Sign in") { authenticate(false) }
        button("Register and sign in") { authenticate(true) }
        button("Sign out") { launchTask { try { if (auth.token() != null) api?.logout() } finally { auth.clear(); controller?.clear(); settingsScreen(); message.text = "Signed out locally." } } }
        button("Scan / view annotations") { if (saveServer()) scanScreen() }
        button("RayNeo binocular viewer") {
            if (saveServer() && !DeviceIntegration.launch(this)) message.text = "Mercury SDK not installed in this build. Use the standard screen-space viewer; see RAYNEO_SETUP.md."
        }
        button("Open companion web interface") {
            if (saveServer()) try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(api!!.baseUrl))) } catch (_: Exception) { message.text = "Open ${api!!.baseUrl} on your companion computer." }
        }
    }
    private fun scanScreen() {
        inScan = true; baseScreen()
        label(auth.session?.takeIf { auth.token() != null }?.let { "Signed in: ${it.user.username}" } ?: "Guest · public notes only", 18f)
        scanStatus = label("Camera stopped", 16f)
        preview = FramePreview(this).apply {
            visibility = View.GONE
            root.addView(this, LinearLayout.LayoutParams(-1, (resources.configuration.screenHeightDp.div(3).coerceIn(120, 220) * resources.displayMetrics.density).toInt()))
        }
        progress = ProgressBar(this).apply { visibility = View.GONE; root.addView(this, LinearLayout.LayoutParams(-1, 32)) }
        title = label("Select a physical object", 26f)
        card = label("Scan its QR marker to retrieve authorized annotations.", 24f)
        button("Start camera / scan next object") { startCamera(false) }
        button("Detect objects · model") { startCamera(true) }
        button("Stop camera") { stopCamera(); scanStatus?.text = "Camera stopped" }
        button("Previous annotation") { controller?.move(-1) }
        button("Next annotation") { controller?.move(1) }
        button("Annotation details / full text") { details() }
        button("Refresh selected object") { controller?.state?.value?.markerId?.let {
            stopCamera(keepFrame = true); beginTrace(if (simulated) "simulated_refresh" else "refresh", it); controller?.refresh()
        } }
        button("Load more annotations") { controller?.more() }
        button("Register unknown object") { registerObject() }
        button("Create annotation") { createNote() }
        button("Manual marker · SIMULATION") {
            stopCamera()
            val input = EditText(this).apply { hint = "spatial:v1:<UUID> or UUID" }
            AlertDialog.Builder(this).setTitle("SIMULATION · no camera recognition").setView(input).setPositiveButton("Look up") { _, _ ->
                val id = MarkerId.parse(input.text.toString())
                if (id == null) message.text = "Invalid marker UUID" else { simulated = true; beginTrace("simulated_lookup", id); scanStatus?.text = "SIMULATION · manually supplied marker"; controller?.lookup(id) }
            }.setNegativeButton("Cancel", null).show()
        }
        button("Settings / account") { settingsScreen() }
        controller?.state?.value?.let { render(it) }
    }
    private fun startCamera(useModel: Boolean = false) {
        stopCamera(); controller?.clear(); simulated = false; modelMode = useModel
        when (CameraPermissionPolicy.action(ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED,
            prefs.getBoolean("cameraAsked", false), shouldShowRequestPermissionRationale(Manifest.permission.CAMERA))) {
            CameraPermissionPolicy.Action.REQUEST_PERMISSION -> { prefs.edit().putBoolean("cameraAsked", true).apply(); requestPermissions(arrayOf(Manifest.permission.CAMERA), 10) }
            CameraPermissionPolicy.Action.SHOW_SETTINGS -> {
                message.text = "Camera permission denied. Enable it in Android settings, or use explicit simulation mode."
                startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:$packageName")))
            }
            CameraPermissionPolicy.Action.START_CAMERA -> {
                val scan = ++scanGeneration
                beginTrace(if (useModel) "model_detection" else "camera_qr")
                var frames = 0
                val pending = AtomicBoolean(false)
                scanning = true; message.text = if (useModel) "One grayscale camera frame is sent to your configured backend for detection. Confirm the object afterward." else "Aim at one experiment QR label; keep its white border visible."
                scanStatus?.text = "Starting camera…"
                scanTimeout = lifecycleScope.launch {
                    delay(15_000)
                    if (scan == scanGeneration && scanning) {
                        endTrace("recognition_timeout"); stopCamera()
                        scanStatus?.text = if (useModel) "No camera frame available. Stop and retry." else "No marker detected in 15 seconds. Adjust distance/light and scan again."
                    }
                }
                camera.start({ frame ->
                    if (scan == scanGeneration && scanning && pending.compareAndSet(false, true)) {
                        val identity = if (useModel) null else recognizer.recognize(frame)
                        val detectedAt = now()
                        val count = ++frames
                        val bitmap = FramePreview.bitmap(frame, useModel || identity != null)
                        runOnUiThread {
                            pending.set(false)
                            if (scan != scanGeneration || !scanning || !inScan) { bitmap.recycle(); return@runOnUiThread }
                            trace?.frames = count
                            if (useModel && count >= 4) {
                                stopCamera(keepFrame = true, finishTrace = false)
                                detectFrame(bitmap)
                                return@runOnUiThread
                            }
                            preview?.show(bitmap, frame, identity)
                            scanStatus?.text = if (useModel) "Preparing model frame · $count/4 · camera exposure settling" else "Scanning QR · $count frames · ${frame.width}×${frame.height}"
                            if (identity != null) {
                                trace?.apply { marker = identity.markerId; detected = detectedAt }
                                stopCamera(keepFrame = true, finishTrace = false)
                                scanStatus?.text = "Camera QR detected · frozen frame · ${identity.points.size} feature points\nImage-space visualization · scan again for another object"
                                controller?.lookup(identity.markerId)
                            }
                        }
                    }
                }, { status -> runOnUiThread {
                    if (scan == scanGeneration && scanning) {
                        scanStatus?.text = status
                        if (!status.startsWith("Scanning")) { endTrace("camera_error"); stopCamera(); scanStatus?.text = status }
                    }
                } })
            }
        }
    }
    private fun detectFrame(bitmap: android.graphics.Bitmap) {
        val generation = scanGeneration
        preview?.showDetections(bitmap, emptyList())
        progress?.visibility = View.VISIBLE
        scanStatus?.text = "Model detecting… · uploaded camera frame"
        modelJob = lifecycleScope.launch {
            try {
                val bytes = withContext(Dispatchers.Default) {
                    java.io.ByteArrayOutputStream().use { stream ->
                        bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 90, stream); stream.toByteArray()
                    }
                }
                val requestStarted = now()
                val result = api!!.detect(bytes)
                if (generation != scanGeneration || !inScan) return@launch
                val detections = result.detections.filter { it.valid() }
                preview?.showDetections(bitmap, detections)
                progress?.visibility = View.GONE
                scanStatus?.text = "Model: ${detections.size} detections · ${result.inferenceMs.toInt()} ms inference\nCategory only · confirm physical identity"
                Log.i("SpatialVision", com.google.gson.Gson().toJson(mapOf("test_id" to java.util.UUID.randomUUID().toString(), "timestamp" to java.time.Instant.now().toString(), "environment" to trace?.environment, "method" to "model_camera", "http_ms" to now() - requestStarted, "inference_ms" to result.inferenceMs, "detections" to detections.size, "category_detected" to detections.isNotEmpty(), "identity_confirmed" to false)))
                if (detections.isEmpty()) { endTrace("no_model_detection"); message.text = "No confident object found. Adjust framing and try again."; return@launch }
                endTrace()
                modelDialog = AlertDialog.Builder(this@MainActivity).setTitle("Select detected category")
                    .setItems(detections.map { "${it.label} · ${(it.confidence * 100).toInt()}%" }.toTypedArray()) { _, index ->
                        if (generation == scanGeneration && inScan) {
                            preview?.showDetections(bitmap, listOf(detections[index]))
                            chooseModelObject(detections[index].label, generation)
                        }
                    }.setNegativeButton("Cancel") { _, _ -> endTrace("cancelled") }.show()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                if (generation == scanGeneration) {
                    endTrace("model_lookup_error"); progress?.visibility = View.GONE
                    scanStatus?.text = "Model detection failed · retry or use QR"
                    message.text = e.message ?: "Detection failed"
                    if (e is ApiException && e.code == 401) controller?.clear("Session expired. Sign in again.")
                }
            }
        }
    }
    private fun chooseModelObject(label: String, generation: Int) {
        modelJob = lifecycleScope.launch {
            try {
                val objects = api!!.candidates(label)
                if (generation != scanGeneration || !inScan) return@launch
                if (objects.isEmpty()) {
                    endTrace("no_registered_candidates")
                    message.text = "No registered $label objects. Set the object's Visual category in the companion."
                    return@launch
                }
                modelDialog = AlertDialog.Builder(this@MainActivity).setTitle("Confirm which $label")
                    .setItems(objects.map { "${it.name ?: it.markerId} · ${it.markerId.take(8)}" }.toTypedArray()) { _, index ->
                        if (generation == scanGeneration && inScan) {
                            val obj = objects[index]
                            // Confirmation is a human decision, not automatic instance recognition.
                            beginTrace("model_confirmed_lookup", obj.markerId)
                            scanStatus?.text = "MODEL + YOUR CONFIRMATION · ${obj.name}\nImage-space box · no automatic instance identity"
                            controller?.lookup(obj.markerId)
                        }
                    }.setNegativeButton("Cancel") { _, _ -> endTrace("cancelled") }.show()
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { if (generation == scanGeneration) { endTrace("candidate_lookup_error"); message.text = e.message } }
        }
    }
    private fun stopCamera(keepFrame: Boolean = false, finishTrace: Boolean = true) {
        modelJob?.cancel(); modelJob = null
        progress?.visibility = View.GONE
        modelDialog?.dismiss(); modelDialog = null
        if (finishTrace) endTrace("cancelled")
        scanTimeout?.cancel(); scanTimeout = null
        ++scanGeneration; scanning = false; camera.stop()
        if (!keepFrame) preview?.clear()
        if (!keepFrame) scanStatus?.text = "Camera stopped · select Start camera to scan"
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 10 && inScan) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) startCamera(modelMode)
            else message.text = "Camera permission denied. You can use SIMULATION or grant permission in Settings."
        }
    }
    override fun render(state: AnnotationState) {
        message.text = state.message
        progress?.visibility = if (state.loading) View.VISIBLE else View.GONE
        val currentTrace = trace
        if (state.lookupTiming != null && currentTrace?.marker == state.markerId) root.post {
            if (trace === currentTrace && controller?.state?.value == state) endTrace(state = state)
        }
        title?.text = state.physicalObject?.let { "${it.name ?: it.markerId}\n${it.locationLabel ?: ""}" } ?: state.markerId ?: "No object selected"
        card?.text = state.selected?.let { "${state.index + 1}/${state.annotations.size} · ${it.visibility.uppercase()} · ${it.authorUsername}\n${it.content}" } ?: if (state.loading) "Loading…" else "No authorized annotations loaded."
        if (simulated) scanStatus?.text = "SIMULATION · manually supplied marker"
    }
    private fun details() {
        val note = controller?.state?.value?.selected ?: return
        val text = TextView(this).apply { text = "${note.authorUsername} · ${note.createdAt}\n${note.visibility}\n\n${note.content}"; textSize = 22f; setPadding(24, 16, 24, 16) }
        AlertDialog.Builder(this).setTitle("Annotation details").setView(ScrollView(this).apply { addView(text) }).setPositiveButton("Back", null).show()
    }
    private fun registerObject() {
        val state = controller?.state?.value ?: return
        if (!state.unknown || state.markerId == null) { message.text = "Scan an unregistered marker first."; return }
        if (auth.token() == null) { message.text = "Sign in from Settings before registering."; return }
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 12, 24, 12) }
        val name = EditText(this).apply { hint = "Object name (public)"; box.addView(this) }
        val location = EditText(this).apply { hint = "Location label (optional, public)"; box.addView(this) }
        AlertDialog.Builder(this).setTitle("Register object").setView(box).setPositiveButton("Save") { _, _ ->
            launchTask { api!!.createObject(state.markerId, name.text.toString(), LocationContext(location.text.toString(), null, null)); controller?.lookup(state.markerId) }
        }.setNegativeButton("Cancel", null).show()
    }
    private fun createNote() {
        val obj = controller?.state?.value?.physicalObject
        if (obj == null || auth.token() == null) { message.text = "Select a registered object and sign in first."; return }
        launchTask {
            val groups = api!!.groups()
            val box = LinearLayout(this@MainActivity).apply { orientation = LinearLayout.VERTICAL; setPadding(24, 12, 24, 12) }
            val content = EditText(this@MainActivity).apply { hint = "Annotation text"; minLines = 3; box.addView(this) }
            val visibility = Spinner(this@MainActivity).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, listOf("private", "public", "group")); box.addView(this) }
            val group = Spinner(this@MainActivity).apply { adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, listOf("Choose group") + groups.map { it.name }); box.addView(this) }
            val dialog = AlertDialog.Builder(this@MainActivity).setTitle("New annotation").setView(box).setPositiveButton("Save", null).setNegativeButton("Cancel", null).create()
            dialog.setOnShowListener {
                dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                    val chosen = visibility.selectedItem.toString(); val groupId = if (chosen == "group") groups.getOrNull(group.selectedItemPosition - 1)?.id else null
                    if (content.text.isBlank() || content.text.length > 10000 || (chosen == "group" && groupId == null)) { content.error = "Enter 1–10000 characters and select a group when required"; return@setOnClickListener }
                    dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = false
                    launchTask {
                        try { api!!.createAnnotation(obj.id, content.text.toString(), chosen, groupId); dialog.dismiss(); controller?.refresh(); message.text = "Annotation saved." }
                        finally { dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = true }
                    }
                }
            }
            dialog.show()
        }
    }
    override fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        if (inScan && currentFocus !is EditText) when (input.actionForKey(keyCode)) {
            DeviceAction.NEXT -> { controller?.move(1); return true }
            DeviceAction.PREVIOUS -> { controller?.move(-1); return true }
            DeviceAction.DETAILS -> { details(); return true }
            DeviceAction.BACK -> { settingsScreen(); return true }
            else -> Unit // Enter/center activate the focused native control.
        }
        return super.onKeyDown(keyCode, event)
    }
    override fun onPause() { userOperation?.cancel(); savedMarker = controller?.state?.value?.markerId; stopCamera(); controller?.clear("Paused · refresh on return"); super.onPause() }
    override fun onResume() { super.onResume(); if (inScan) savedMarker?.let { controller?.lookup(it) }; savedMarker = null }
    override fun onDestroy() { stopCamera(); collector?.cancel(); super.onDestroy() }
}
