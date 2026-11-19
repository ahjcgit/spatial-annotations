package org.spatial.annotations

import org.junit.Test

class CodexProbeProtocolTest {
    private val hash = "a".repeat(64)
    private fun valid() = ProbeResponse("trial-1", hash, listOf(ProbeLabel("A", "Silver bottle", false), ProbeLabel("B", "Orange bottle", false)))
    @Test fun acceptsBoundedSnapshot() { CodexProbeProtocol.validate(valid(), "trial-1", hash, 1_000_000) }
    @Test(expected = IllegalArgumentException::class) fun rejectsPreviousRequest() { CodexProbeProtocol.validate(valid(), "trial-2", hash, 1_000_000) }
    @Test(expected = IllegalArgumentException::class) fun rejectsDifferentImage() { CodexProbeProtocol.validate(valid(), "trial-1", "b".repeat(64), 1_000_000) }
    @Test(expected = IllegalArgumentException::class) fun rejectsExpiredSource() { CodexProbeProtocol.validate(valid(), "trial-1", hash, CodexProbeProtocol.MAX_SOURCE_AGE_NS + 1) }
    @Test(expected = IllegalArgumentException::class) fun rejectsDuplicateIdentity() { CodexProbeProtocol.validate(valid().copy(labels = listOf(ProbeLabel("A", "one", false), ProbeLabel("A", "two", false))), "trial-1", hash, 0) }
    @Test(expected = IllegalArgumentException::class) fun rejectsControlText() { CodexProbeProtocol.validate(valid().copy(labels = listOf(ProbeLabel("A", "bad\nlabel", false))), "trial-1", hash, 0) }
    @Test fun permitsAbstention() { CodexProbeProtocol.validate(valid().copy(labels = emptyList()), "trial-1", hash, 0) }
}
