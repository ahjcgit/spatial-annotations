package org.spatial.annotations

import java.nio.ByteBuffer
import org.junit.Assert.*
import org.junit.Test

class YPlanePackingTest {
    @Test fun directBufferWithOffsetAndRowPadding() {
        val source = ByteBuffer.allocateDirect(10)
        source.put(byteArrayOf(99, 1, 2, 3, 88, 88, 4, 5, 6, 88)).position(1)
        assertArrayEquals(byteArrayOf(1, 2, 3, 4, 5, 6), YPlanePacking.copy(source, 3, 2, 5, 1))
        assertEquals(1, source.position())
    }
    @Test fun interleavedPixelsWithoutTrailingPadding() {
        val source = ByteBuffer.wrap(byteArrayOf(1, 99, 2, 99, 3, 88, 4, 99, 5, 99, 6))
        assertArrayEquals(byteArrayOf(1, 2, 3, 4, 5, 6), YPlanePacking.copy(source, 3, 2, 6, 2))
    }
}
