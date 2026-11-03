package org.spatial.annotations

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.lang.reflect.Type
import java.util.concurrent.TimeUnit

class ApiException(val code: Int, message: String) : IOException(message)
object ServerAddress {
    fun normalize(input: String, allowLanHttp: Boolean): String {
        val url = input.trim().toHttpUrl()
        require(url.username.isEmpty() && url.password.isEmpty() && url.query == null && url.fragment == null) { "Use a server URL without credentials, query or fragment" }
        require(url.encodedPath == "/") { "Use a root server URL, without a path" }
        val parts = url.host.split('.').mapNotNull { it.toIntOrNull() }
        val lan = parts.size == 4 && parts.all { it in 0..255 } && (parts[0] == 10 || (parts[0] == 192 && parts[1] == 168) || (parts[0] == 172 && parts[1] in 16..31))
        val usbLoopback = url.host == "127.0.0.1"
        require(url.scheme == "https" || (allowLanHttp && (lan || usbLoopback))) { "Use HTTPS, or debug HTTP to a private LAN IPv4 address / 127.0.0.1 via ADB reverse" }
        return url.toString().trimEnd('/')
    }
}

class ApiClient(val baseUrl: String, private val auth: AuthState,
                private val client: OkHttpClient = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS)
                    .readTimeout(15, TimeUnit.SECONDS).callTimeout(20, TimeUnit.SECONDS)
                    .followRedirects(false).followSslRedirects(false).build()) {
    private val gson = Gson()
    private suspend fun <T> request(path: String, type: Type, method: String = "GET", body: Any? = null): T = withContext(Dispatchers.IO) {
        val builder = Request.Builder().url(baseUrl + path).header("Accept", "application/json")
        auth.token()?.let { builder.header("Authorization", "Bearer $it") }
        if (method != "GET") builder.method(method, gson.toJson(body ?: emptyMap<String, String>()).toRequestBody("application/json".toMediaType()))
        client.newCall(builder.build()).execute().use { response ->
            if (response.code == 401) auth.clear()
            if (!response.isSuccessful) {
                val message = when (response.code) {
                    401 -> "Session expired or invalid credentials. Sign in again."
                    403 -> "You do not have permission for this action."
                    404 -> "Not found or not visible to this user."
                    409 -> "Already registered. Look up the marker or use another username."
                    422 -> "Invalid input. Check text, marker ID and group selection."
                    else -> "Server request failed (${response.code})."
                }
                throw ApiException(response.code, message)
            }
            if (type == Unit::class.java) @Suppress("UNCHECKED_CAST") (Unit as T)
            else gson.fromJson<T>(response.body?.string() ?: throw IOException("Empty server response"), type)
        }
    }
    suspend fun login(username: String, password: String): LoginResponse = request("/auth/login", LoginResponse::class.java, "POST", mapOf("username" to username, "password" to password))
    suspend fun register(username: String, password: String): User = request("/auth/register", User::class.java, "POST", mapOf("username" to username, "password" to password))
    suspend fun logout(): Unit = request("/auth/logout", Unit::class.java, "POST")
    suspend fun lookup(marker: String): PhysicalObject = request("/objects/by-marker/$marker", PhysicalObject::class.java)
    suspend fun annotations(id: String, offset: Int = 0): List<Annotation> = request("/objects/$id/annotations?limit=100&offset=$offset", object : TypeToken<List<Annotation>>() {}.type)
    suspend fun groups(): List<Group> = request("/groups", object : TypeToken<List<Group>>() {}.type)
    suspend fun createObject(marker: String, name: String, location: LocationContext?): PhysicalObject = request("/objects", PhysicalObject::class.java, "POST",
        mapOf("marker_id" to marker, "name" to name, "location_label" to location?.label, "latitude" to location?.latitude, "longitude" to location?.longitude))
    suspend fun createAnnotation(objectId: String, content: String, visibility: String, groupId: String?): Annotation = request("/annotations", Annotation::class.java, "POST",
        mapOf("object_id" to objectId, "content" to content, "visibility" to visibility, "group_id" to groupId))
}

interface AnnotationRepository { suspend fun lookup(marker: String): PhysicalObject; suspend fun annotations(objectId: String, offset: Int = 0): List<Annotation> }
class NetworkAnnotationRepository(private val api: ApiClient) : AnnotationRepository {
    override suspend fun lookup(marker: String) = api.lookup(marker)
    override suspend fun annotations(objectId: String, offset: Int) = api.annotations(objectId, offset)
}
