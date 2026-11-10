package org.spatial.annotations

import java.time.Instant

interface TokenStore { fun read(): String?; fun write(value: String?); }
data class Session(val token: String, val expiresAt: String, val user: User)
class AuthState(private val store: TokenStore, private val now: () -> Instant = Instant::now) {
    private val gson = com.google.gson.Gson()
    @Volatile var session: Session? = runCatching { store.read()?.let { gson.fromJson(it, Session::class.java) } }.getOrNull()
        private set
    @Synchronized fun token(): String? {
        val current = session ?: return null
        if (runCatching { Instant.parse(current.expiresAt) <= now() }.getOrDefault(true)) { clear(); return null }
        return current.token
    }
    @Synchronized fun save(response: LoginResponse) { session = Session(response.accessToken, response.expiresAt, response.user); store.write(gson.toJson(session)) }
    @Synchronized fun clearIfToken(expected: String?) { if (session?.token == expected) clear() }
    @Synchronized fun clear() { session = null; store.write(null) }
}
