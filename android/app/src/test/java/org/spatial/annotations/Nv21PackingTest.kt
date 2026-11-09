package org.spatial.annotations
import org.junit.Assert.*
import org.junit.Test
class Nv21PackingTest {
    @Test fun preservesLuminanceAndInterleavesVBeforeU() {
        val y = byteArrayOf(1, 2, 3, 4)
        assertArrayEquals(byteArrayOf(1, 2, 3, 4, 90, 40), Nv21Packing.pack(y, byteArrayOf(40), byteArrayOf(90)))
        assertArrayEquals(byteArrayOf(1, 2, 3, 4), y)
    }
}
