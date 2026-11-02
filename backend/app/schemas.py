import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)

    @field_validator("created_at", "updated_at", "expires_at", check_fields=False)
    @classmethod
    def utc_timestamp(cls, value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

    @field_validator("spatial_metadata", "spatial_anchor", check_fields=False)
    @classmethod
    def bounded_metadata(cls, value):
        if value is not None and len(json.dumps(value, allow_nan=False)) > 8192:
            raise ValueError("Spatial metadata must be at most 8192 characters")
        return value


class Credentials(Schema):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=10, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        return value.lower()

    # Preserve password whitespace; usernames and content are otherwise trimmed.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class UserOut(Schema):
    id: str
    username: str
    created_at: datetime


class TokenOut(Schema):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class GroupCreate(Schema):
    name: str = Field(min_length=1, max_length=100)


class GroupOut(GroupCreate):
    id: str
    owner_id: str
    created_at: datetime
    member_ids: list[str]


class MemberCreate(Schema):
    username: str = Field(min_length=3, max_length=40)


class ObjectFields(Schema):
    name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    reference_image: str | None = Field(default=None, max_length=1000, pattern=r"^https://")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    location_label: str | None = Field(default=None, max_length=120)
    spatial_metadata: dict | None = None


class ObjectCreate(ObjectFields):
    marker_id: UUID

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Supply both latitude and longitude")
        return self


class ObjectPatch(ObjectFields):
    pass


class ObjectOut(ObjectFields):
    id: str
    marker_id: str
    creator_id: str
    created_at: datetime


Visibility = Literal["public", "private", "group"]


class AnnotationCreate(Schema):
    object_id: UUID
    content: str = Field(min_length=1, max_length=10000)
    visibility: Visibility = "private"
    group_id: UUID | None = None
    spatial_anchor: dict | None = None

    @model_validator(mode="after")
    def group_consistency(self):
        if (self.visibility == "group") != (self.group_id is not None):
            raise ValueError("group_id is required only for group visibility")
        return self


class AnnotationPatch(Schema):
    content: str | None = Field(default=None, min_length=1, max_length=10000)
    visibility: Visibility | None = None
    group_id: UUID | None = None
    spatial_anchor: dict | None = None

    @model_validator(mode="after")
    def no_null_required(self):
        for key in ("content", "visibility"):
            if key in self.model_fields_set and getattr(self, key) is None:
                raise ValueError(f"{key} cannot be null")
        return self


class AnnotationOut(Schema):
    id: str
    object_id: str
    content: str
    author_id: str
    author_username: str
    created_at: datetime
    updated_at: datetime
    visibility: Visibility
    group_id: str | None
    spatial_anchor: dict | None
