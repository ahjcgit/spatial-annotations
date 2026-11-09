package org.spatial.annotations

import android.content.Context
import android.graphics.*
import android.view.View
import kotlin.math.min

/** Owns only the current bitmap. Replaced rendered bitmaps are left to Android/GC, never recycled while RenderThread may use them. */
class FramePreview(context: Context) : View(context) {
    private var bitmap: Bitmap? = null
    private var imageSize = ImageSize(1, 1)
    private var points = emptyList<ImagePoint>()
    private val destination = RectF()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { isFilterBitmap = true }
    fun show(bitmap: Bitmap, frame: CameraFrame, identity: ObjectIdentity?) {
        this.bitmap = bitmap
        imageSize = FrameGeometry.size(frame.width, frame.height, frame.sensorRotation)
        points = identity?.points.orEmpty().map { FrameGeometry.rotate(it, frame.width, frame.height, frame.sensorRotation) }
        contentDescription = if (identity == null) "Live grayscale camera preview" else
            "Frozen recognized frame. ${points.size} QR feature centers highlighted; not a bounding box."
        visibility = VISIBLE; invalidate()
    }
    fun clear() { bitmap = null; points = emptyList(); visibility = GONE; invalidate() }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val image = bitmap ?: return
        val scale = min(width.toFloat() / imageSize.width, height.toFloat() / imageSize.height)
        val left = (width - imageSize.width * scale) / 2
        val top = (height - imageSize.height * scale) / 2
        paint.style = Paint.Style.FILL; paint.color = Color.WHITE
        destination.set(left, top, width - left, height - top)
        canvas.drawBitmap(image, null, destination, paint)
        val radius = 7f * resources.displayMetrics.density
        points.forEach {
            val p = FrameGeometry.fit(it, imageSize, width, height)
            paint.style = Paint.Style.STROKE; paint.strokeWidth = 5f; paint.color = Color.BLACK
            canvas.drawCircle(p.x, p.y, radius, paint)
            paint.strokeWidth = 3f; paint.color = Color.YELLOW
            canvas.drawCircle(p.x, p.y, radius, paint)
        }
    }
    companion object {
        /** Called on the camera worker, never the UI thread. */
        fun bitmap(frame: CameraFrame, frozen: Boolean): Bitmap {
            val step = maxOf(1, maxOf(frame.width, frame.height) / if (frozen) 960 else 480)
            val width = frame.width / step; val height = frame.height / step
            val pixels = IntArray(width * height) { i ->
                val gray = frame.luminance[(i / width * step) * frame.width + (i % width * step)].toInt() and 255
                Color.rgb(gray, gray, gray)
            }
            val raw = Bitmap.createBitmap(pixels, width, height, Bitmap.Config.ARGB_8888)
            return if (FrameGeometry.rotation(frame.sensorRotation) == 0) raw else Bitmap.createBitmap(raw, 0, 0, width, height,
                Matrix().apply { postRotate(frame.sensorRotation.toFloat()) }, true).also { if (it !== raw) raw.recycle() }
        }
    }
}
