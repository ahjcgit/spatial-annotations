from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, ForeignKey, DateTime, Float, JSON, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionToken(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Group(Base):
    __tablename__ = "groups"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = "memberships"
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)


class PhysicalObject(Base):
    __tablename__ = "objects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    marker_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    reference_image: Mapped[str | None] = mapped_column(String(1000))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    location_label: Mapped[str | None] = mapped_column(String(120), index=True)
    spatial_metadata: Mapped[dict | None] = mapped_column(JSON)
    creator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        CheckConstraint("latitude IS NULL OR (latitude >= -90 AND latitude <= 90)"),
        CheckConstraint("longitude IS NULL OR (longitude >= -180 AND longitude <= 180)"),
        CheckConstraint("(latitude IS NULL AND longitude IS NULL) OR (latitude IS NOT NULL AND longitude IS NOT NULL)"),
    )


class Annotation(Base):
    __tablename__ = "annotations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    object_id: Mapped[str] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    visibility: Mapped[str] = mapped_column(String(10), index=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("groups.id"), index=True)
    spatial_anchor: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        CheckConstraint("visibility IN ('public','private','group')"),
        CheckConstraint("(visibility = 'group' AND group_id IS NOT NULL) OR (visibility != 'group' AND group_id IS NULL)"),
        Index("ix_annotation_object_time", "object_id", "created_at", "id"),
    )
