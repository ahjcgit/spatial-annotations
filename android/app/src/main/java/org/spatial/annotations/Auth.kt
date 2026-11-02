package org.spatial.annotations

import java.time.Instant

interface TokenStore { fun read(): String?; fun write(value: String?); }
data class Session(val token: String, val expiresAt: String, val user: User)
class AuthState(private val store: TokenStore, private val now: () -> Instant = Instant::now) {
    private val gson = com.google.gson.Gson()
    var session: Session? = runCatching { store.read()?.let { gson.fromJson(it, Session::class.java) } }.getOrNull()
        private set
    fun token(): String? {
        val current = session ?: return null
        if (runCatching { Instant.parse(current.expiresAt) <= now() }.getOrDefault(true)) { clear(); return null }
        return current.token
    }
    fun save(response: LoginResponse) { session = Session(response.accessToken, response.expiresAt, response.user); store.write(gson.toJson(session)) }
    fun clear() { session = null; store.write(null) }
}
