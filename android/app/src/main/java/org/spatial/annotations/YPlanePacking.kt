package org.spatial.annotations

import java.nio.ByteBuffer

object YPlanePacking {
    fun copy(source: ByteBuffer, width: Int, height: Int, rowStride: Int, pixelStride: Int): ByteArray {
        val buffer = source.duplicate()
        val origin = buffer.position()
        val packed = ByteArray(width * height)
        val row = if (pixelStride == 1) null else ByteArray((width - 1) * pixelStride + 1)
        for (y in 0 until height) {
            buffer.position(origin + y * rowStride)
            if (row == null) buffer.get(packed, y * width, width)
            else {
                buffer.get(row)
                for (x in 0 until width) packed[y * width + x] = row[x * pixelStride]
            }
        }
        return packed
    }
}
