package org.spatial.annotations

import com.google.gson.GsonBuilder
import com.google.gson.JsonParser
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File
import java.time.Instant

class ReplayTest {
    @Test fun replayCapturedOrGeneratedFramesThroughProductionDecoder() {
        val path = System.getProperty("replayDir")
        assumeTrue("Supply -PreplayDir=/absolute/fixture/directory", !path.isNullOrBlank())
        val directory = File(path!!)
        val fixtures = JsonParser.parseString(File(directory,"manifest.json").readText()).asJsonArray
        val rows = mutableListOf<Map<String,Any?>>()
        val failures = mutableListOf<String>()
        for (entry in fixtures) {
            val item = entry.asJsonObject
            val width = item["width"].asInt; val height = item["height"].asInt
            val pixels = File(directory,item["luminance_file"].asString).readBytes()
            assertEquals(width*height,pixels.size)
            val expected = item["expected_marker"].takeUnless { it.isJsonNull }?.asString
            val started = System.nanoTime()
            val decoded = QrObjectRecognizer().recognize(CameraFrame(pixels,width,height,started,item["rotation"].asInt))
            val elapsed = (System.nanoTime()-started)/1_000_000.0
            val matched = decoded?.markerId == expected
            if (!matched) failures.add(item["file"].asString)
            decoded?.points?.forEach { assertTrue(it.x >= 0 && it.y >= 0 && it.x < width && it.y < height) }
            rows.add(linkedMapOf("test_id" to item["file"].asString,"timestamp" to Instant.now().toString(),
                "environment" to item["environment"].asString,"identification_method" to "offline_qr_replay",
                "marker_uuid" to decoded?.markerId,"recognition_success" to (decoded!=null),
                "recognition_latency_ms" to elapsed,"total_latency_ms" to elapsed,"frames_processed" to 1,
                "backend_success" to null,"backend_latency_ms" to null,"annotation_count" to null,
                "expected_marker" to expected,"expectation_match" to matched,"feature_points" to decoded?.points,
                "failure_category" to if (matched) null else "unexpected_recognition_result"))
        }
        val gson = GsonBuilder().serializeNulls().create()
        File(directory,"replay-results.jsonl").writeText(rows.joinToString("\n",postfix="\n") { gson.toJson(it) })
        assertTrue("Replay failures: $failures",failures.isEmpty())
        assertTrue(fixtures.size()>0)
    }
}
