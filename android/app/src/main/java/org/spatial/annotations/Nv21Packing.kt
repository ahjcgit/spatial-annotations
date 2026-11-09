package org.spatial.annotations
object Nv21Packing {
    fun pack(y: ByteArray, u: ByteArray, v: ByteArray): ByteArray {
        require(u.size == v.size)
        val output = y.copyOf(y.size + u.size + v.size)
        for (i in u.indices) { output[y.size + i * 2] = v[i]; output[y.size + i * 2 + 1] = u[i] }
        return output
    }
}
