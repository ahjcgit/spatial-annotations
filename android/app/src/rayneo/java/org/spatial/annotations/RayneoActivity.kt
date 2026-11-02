package org.spatial.annotations

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.SystemClock
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.ffalcon.mercury.android.sdk.touch.TempleAction
import com.ffalcon.mercury.android.sdk.ui.activity.BaseMirrorActivity
import org.spatial.annotations.databinding.ActivityRayneoBinding
import kotlinx.coroutines.launch

/** Opt-in adapter. API symbols checked against RayNeo OpenClaw source; not compiled without licensed AAR. */
class RayneoActivity : BaseMirrorActivity<ActivityRayneoBinding>(), AnnotationRenderer {
    private lateinit var controller: ScanController
    private val camera by lazy { Camera2Capture(this) }
    private val recognizer = QrObjectRecognizer()
    private var scanning = false
    private var detail = false
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val server = getSharedPreferences("settings", MODE_PRIVATE).getString("server", "") ?: ""
        try {
            val api = ApiClient(ServerAddress.normalize(server, BuildConfig.DEBUG), AuthState(SecureTokenStore(this)))
            controller = ScanController(NetworkAnnotationRepository(api), lifecycleScope)
        } catch (_: Exception) { finish(); return }
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.RESUMED) {
                launch { controller.state.collect { render(it) } }
                launch {
                    templeActionViewModel.state.collect { action ->
                        when (action) {
                            is TempleAction.Click -> {
                                if (controller.state.value.selected == null) scan() else { detail = !detail; render(controller.state.value) }
                            }
                            is TempleAction.DoubleClick -> finish()
                            is TempleAction.TripleClick -> { controller.clear(); detail = false; scan() }
                            is TempleAction.SlideForward -> { detail = false; controller.move(1) }
                            is TempleAction.SlideBackward -> { detail = false; controller.move(-1) }
                            is TempleAction.SlideUpwards -> mBindingPair.updateView { scroll.smoothScrollBy(0, -160) }
                            is TempleAction.SlideDownwards -> mBindingPair.updateView { scroll.smoothScrollBy(0, 160) }
                            else -> Unit
                        }
                    }
                }
            }
        }
    }
    private fun scan() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), 11); return
        }
        scanning = true
        camera.start({ frame -> recognizer.recognize(frame)?.let { identity -> runOnUiThread {
            if (scanning) { scanning = false; camera.stop(); controller.markerSeen(identity.markerId, SystemClock.elapsedRealtime()) }
        } } }, { message -> runOnUiThread { if (scanning) mBindingPair.updateView { status.text = message } } })
    }
    override fun render(state: AnnotationState) {
        val note = state.selected
        val text = if (note == null) "${state.message}\nTap to scan. Create/register using the companion or standard viewer."
            else "${state.index + 1}/${state.annotations.size} · ${note.visibility}\n" + (if (detail) "${note.authorUsername} · ${note.createdAt}\n\n" else "") + note.content
        // This callback runs once per eye: only update views here, never mutate shared state.
        mBindingPair.updateView {
            status.text = "Head-locked · triple tap to rescan"
            objectTitle.text = state.physicalObject?.name ?: state.markerId ?: "Spatial Notes"
            content.text = text
        }
    }
    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 11) {
            if (grantResults.firstOrNull() == PackageManager.PERMISSION_GRANTED) scan()
            else mBindingPair.updateView { status.text = "Camera denied. Grant permission in Android settings." }
        }
    }
    override fun onPause() {
        scanning = false; camera.stop(); if (::controller.isInitialized) controller.clear("Paused; tap to scan again")
        super.onPause()
    }
}
