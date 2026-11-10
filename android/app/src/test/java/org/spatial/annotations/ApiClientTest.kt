package org.spatial.annotations

import kotlinx.coroutines.*
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.SocketPolicy
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

class ApiClientTest {
    @Test fun parsesLoginObjectsAndNotesWithAuthorization() = runBlocking {
        MockWebServer().use { server ->
            server.start()
            val auth = AuthState(MemoryTokens())
            val api = ApiClient(server.url("/").toString().trimEnd('/'), auth)
            server.enqueue(MockResponse().setBody("""{"access_token":"session","expires_at":"2999-01-01T00:00:00Z","user":{"id":"user","username":"alice"}}"""))
            val result = api.login("alice", "password")
            auth.save(result)
            assertEquals("alice", result.user.username)
            val loginRequest = server.takeRequest()
            assertEquals("/auth/login", loginRequest.path); assertNull(loginRequest.getHeader("Authorization"))
            server.enqueue(MockResponse().setBody("""{"id":"object","marker_id":"marker","name":"Mug","location_label":null}"""))
            assertEquals("Mug", api.lookup("marker").name)
            val request = server.takeRequest(); assertEquals("Bearer session", request.getHeader("Authorization")); assertEquals("/objects/by-marker/marker", request.path)
            server.enqueue(MockResponse().setBody("""[{"id":"note","object_id":"object","content":"Use carefully","author_id":"user","author_username":"alice","created_at":"2026-01-01T00:00:00Z","visibility":"public","group_id":null}]"""))
            val notes = api.annotations("object")
            assertEquals("Use carefully", notes.single().content); assertEquals("alice", notes.single().authorUsername)
            assertEquals("/objects/object/annotations?limit=100&offset=0", server.takeRequest().path)
        }
    }
    @Test fun unauthorizedClearsTokenAndRedirectsAreNotFollowed() = runBlocking {
        MockWebServer().use { server ->
            server.start(); val auth = AuthState(MemoryTokens())
            auth.save(LoginResponse("session", "2999-01-01T00:00:00Z", User("u", "alice")))
            val api = ApiClient(server.url("/").toString().trimEnd('/'), auth)
            server.enqueue(MockResponse().setResponseCode(401).setBody("""{"detail":"Invalid session"}"""))
            try { api.annotations("o"); fail("Expected error") } catch (e: ApiException) { assertEquals(401, e.code) }
            assertNull(auth.token()); server.takeRequest()
            server.enqueue(MockResponse().setResponseCode(302).setHeader("Location", "https://example.org/"))
            try { api.lookup("m"); fail("Expected redirect refusal") } catch (e: ApiException) { assertEquals(302, e.code) }
        }
    }
    @Test fun cancellationStopsPendingHttpAndOldUnauthorizedCannotClearNewSession() = runBlocking {
        MockWebServer().use { server ->
            server.start()
            val auth = AuthState(MemoryTokens())
            auth.save(LoginResponse("old", "2999-01-01T00:00:00Z", User("u", "alice")))
            val transport = OkHttpClient.Builder().callTimeout(3, TimeUnit.SECONDS).build()
            val api = ApiClient(server.url("/").toString().trimEnd('/'),auth,transport)
            server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.NO_RESPONSE))
            val waiting = launch { api.lookup("marker") }
            withContext(Dispatchers.IO) { assertNotNull(server.takeRequest(2,TimeUnit.SECONDS)) }
            withTimeout(1000) { waiting.cancelAndJoin() }
            assertTrue(waiting.isCancelled)
            server.enqueue(MockResponse().setResponseCode(401).setHeadersDelay(200,TimeUnit.MILLISECONDS))
            val oldRequest = async { runCatching { api.lookup("marker") } }
            withContext(Dispatchers.IO) { assertNotNull(server.takeRequest(2,TimeUnit.SECONDS)) }
            auth.save(LoginResponse("new", "2999-01-01T00:00:00Z", User("b", "bob")))
            assertTrue(oldRequest.await().exceptionOrNull() is ApiException)
            assertEquals("new",auth.token())
        }
    }

}
