package org.spatial.annotations

import com.google.gson.JsonParser
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.File

/** Optional integration of the production Android HTTP client with the actual running FastAPI service. */
class LiveBackendTest {
    @Test fun twoUsersResolveBothMarkersThroughRealHttp() = runBlocking {
        val path = System.getProperty("demoData")
        assumeTrue("Supply -PdemoData=/absolute/demo-data.json with running backend", !path.isNullOrBlank())
        val data = JsonParser.parseString(File(path!!).readText()).asJsonObject
        val users = data["users"].asJsonArray
        val objects = data["objects"].asJsonArray
        for ((index, user) in users.withIndex()) {
            val auth = AuthState(MemoryTokens())
            val api = ApiClient(data["backend"].asString, auth)
            auth.save(api.login(user.asJsonObject["username"].asString,user.asJsonObject["password"].asString))
            try {
                repeat(3) {
                    for ((objectIndex, entry) in objects.withIndex()) {
                        val expected = entry.asJsonObject
                        val obj = api.lookup(expected["marker_id"].asString)
                        assertEquals(expected["id"].asString,obj.id)
                        val notes = api.annotations(obj.id)
                        assertTrue(notes.all { it.objectId == obj.id })
                        if (objectIndex == 0) {
                            assertTrue(notes.any { it.visibility == "public" })
                            assertTrue(notes.any { it.visibility == "group" })
                            assertEquals(index == 0,notes.any { it.visibility == "private" })
                        } else assertTrue(notes.isEmpty())
                    }
                }
            } finally { api.logout();auth.clear() }
            assertNull(auth.token())
        }
    }
}
