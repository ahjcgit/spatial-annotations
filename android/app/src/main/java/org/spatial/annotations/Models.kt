package org.spatial.annotations

import com.google.gson.annotations.SerializedName

data class User(val id: String, val username: String)
data class LoginResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("expires_at") val expiresAt: String,
    val user: User
)
data class PhysicalObject(
    val id: String,
    @SerializedName("marker_id") val markerId: String,
    val name: String?,
    @SerializedName("location_label") val locationLabel: String? = null,
    val latitude: Double? = null, val longitude: Double? = null
)
data class Annotation(
    val id: String,
    @SerializedName("object_id") val objectId: String,
    val content: String,
    @SerializedName("author_id") val authorId: String,
    @SerializedName("author_username") val authorUsername: String,
    @SerializedName("created_at") val createdAt: String,
    val visibility: String,
    @SerializedName("group_id") val groupId: String? = null
)
data class Group(val id: String, val name: String)
data class LocationContext(val label: String?, val latitude: Double?, val longitude: Double?)

data class AnnotationState(
    val markerId: String? = null, val physicalObject: PhysicalObject? = null,
    val annotations: List<Annotation> = emptyList(), val index: Int = 0,
    val loading: Boolean = false, val message: String = "Ready to scan", val unknown: Boolean = false
) {
    val selected: Annotation? get() = annotations.getOrNull(index)
    fun move(delta: Int) = copy(index = if (annotations.isEmpty()) 0 else Math.floorMod(index + delta, annotations.size))
}
