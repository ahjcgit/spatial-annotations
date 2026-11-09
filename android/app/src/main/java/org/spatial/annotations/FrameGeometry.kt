package org.spatial.annotations

import kotlin.math.min

/** ZXing feature centers, NOT QR corners or a calibrated object bounding box. */
data class ImagePoint(val x: Float, val y: Float)
data class ImageSize(val width: Int, val height: Int)
object FrameGeometry {
    fun rotation(degrees: Int): Int = Math.floorMod(degrees, 360).also { require(it % 90 == 0) }
    // Display.getRotation is counterclockwise; all drawing transforms below are clockwise.
    fun bufferRotation(sensor: Int, display: Int, front: Boolean) = rotation(if (front) display - sensor else sensor + display)
    fun size(width: Int, height: Int, degrees: Int) =
        if (rotation(degrees) % 180 == 0) ImageSize(width, height) else ImageSize(height, width)
    fun rotate(point: ImagePoint, width: Int, height: Int, degrees: Int): ImagePoint = when (rotation(degrees)) {
        90 -> ImagePoint(height - 1f - point.y, point.x)
        180 -> ImagePoint(width - 1f - point.x, height - 1f - point.y)
        270 -> ImagePoint(point.y, width - 1f - point.x)
        else -> point
    }
    fun validPoints(points: List<ImagePoint>, width: Int, height: Int) = points.filter {
        it.x.isFinite() && it.y.isFinite() && it.x >= 0 && it.y >= 0 && it.x < width && it.y < height
    }
    /** Pixel centers mapped to a FIT_CENTER canvas, including letterboxing. */
    fun fit(point: ImagePoint, image: ImageSize, viewWidth: Int, viewHeight: Int): ImagePoint {
        val scale = min(viewWidth.toFloat() / image.width, viewHeight.toFloat() / image.height)
        return ImagePoint((viewWidth - image.width * scale) / 2 + (point.x + .5f) * scale,
            (viewHeight - image.height * scale) / 2 + (point.y + .5f) * scale)
    }
}
