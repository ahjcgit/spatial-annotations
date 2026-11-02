import io
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
import qrcode
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, or_, and_, text, delete
from sqlalchemy.exc import IntegrityError
from .database import Base, configure_database
from .models import User, Group, Membership, PhysicalObject, Annotation, SessionToken
from .schemas import (Credentials, UserOut, TokenOut, GroupCreate, GroupOut, MemberCreate,
                      ObjectCreate, ObjectPatch, ObjectOut, AnnotationCreate, AnnotationPatch, AnnotationOut)
from .security import db_session, require_user, optional_user, bearer, digest, hasher, check_password, issue_token, DUMMY_HASH


def create_app(database_url=None):
    engine, factory = configure_database(database_url)

    @asynccontextmanager
    async def lifespan(app):
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Shared Spatial Annotations", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.session_factory = factory
    ttl = int(os.getenv("TOKEN_TTL_HOURS", "24"))
    if not 1 <= ttl <= 720:
        raise ValueError("TOKEN_TTL_HOURS must be 1..720")

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        # Never echo credentials/content/metadata in validation errors.
        return JSONResponse(status_code=422, content={"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]})

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'" if request.url.path in ("/", "/static/app.js", "/static/style.css") else "frame-ancestors 'none'"
        return response

    def commit(db, message="Conflicting record"):
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, message)

    def get_object(db, object_id):
        obj = db.get(PhysicalObject, str(object_id))
        if obj is None:
            raise HTTPException(404, "Object not found")
        return obj

    def member(db, group_id, user_id):
        return db.get(Membership, (str(group_id), user_id)) is not None

    def visibility_clause(user):
        public = Annotation.visibility == "public"
        if user is None:
            return public
        memberships = select(Membership.group_id).where(Membership.user_id == user.id)
        return or_(public, and_(Annotation.visibility == "private", Annotation.author_id == user.id),
                   and_(Annotation.visibility == "group", Annotation.group_id.in_(memberships)))

    def visible_annotation(db, annotation_id, user):
        annotation = db.scalar(select(Annotation).where(Annotation.id == str(annotation_id), visibility_clause(user)))
        if annotation is None:
            raise HTTPException(404, "Annotation not found")
        return annotation

    def serialize_annotation(db, annotation):
        return AnnotationOut(**{column.name: getattr(annotation, column.name) for column in Annotation.__table__.columns},
                             author_username=db.get(User, annotation.author_id).username)

    def group_out(db, group):
        return GroupOut(id=group.id, name=group.name, owner_id=group.owner_id, created_at=group.created_at,
                        member_ids=list(db.scalars(select(Membership.user_id).where(Membership.group_id == group.id))))

    @app.get("/health")
    def health(db=Depends(db_session)):
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/auth/register", response_model=UserOut, status_code=201)
    def register(data: Credentials, db=Depends(db_session)):
        user = User(username=data.username, password_hash=hasher.hash(data.password))
        db.add(user)
        commit(db, "Username already registered")
        return user

    @app.post("/auth/login", response_model=TokenOut)
    def login(data: Credentials, db=Depends(db_session)):
        user = db.scalar(select(User).where(User.username == data.username))
        valid = check_password(user.password_hash if user else DUMMY_HASH, data.password)
        if not user or not valid:
            raise HTTPException(401, "Invalid username or password")
        return issue_token(db, user, ttl)

    @app.post("/auth/logout", status_code=204)
    def logout(user=Depends(require_user), credentials=Depends(bearer), db=Depends(db_session)):
        db.execute(delete(SessionToken).where(SessionToken.token_hash == digest(credentials.credentials)))
        db.commit()
        return Response(status_code=204)

    @app.get("/users/me", response_model=UserOut)
    def me(user=Depends(require_user)):
        return user

    @app.post("/groups", response_model=GroupOut, status_code=201)
    def create_group(data: GroupCreate, user=Depends(require_user), db=Depends(db_session)):
        group = Group(name=data.name, owner_id=user.id)
        db.add(group)
        db.flush()
        db.add(Membership(group_id=group.id, user_id=user.id))
        commit(db)
        return group_out(db, group)

    @app.get("/groups", response_model=list[GroupOut])
    def groups(user=Depends(require_user), db=Depends(db_session)):
        records = db.scalars(select(Group).join(Membership).where(Membership.user_id == user.id).order_by(Group.created_at))
        return [group_out(db, group) for group in records]

    @app.post("/groups/{group_id}/members", response_model=GroupOut)
    def add_member(group_id: UUID, data: MemberCreate, user=Depends(require_user), db=Depends(db_session)):
        group = db.get(Group, str(group_id))
        if not group or group.owner_id != user.id:
            raise HTTPException(404, "Owned group not found")
        target = db.scalar(select(User).where(User.username == data.username.lower()))
        if not target:
            raise HTTPException(404, "User not found")
        if not member(db, group.id, target.id):
            db.add(Membership(group_id=group.id, user_id=target.id))
            commit(db)
        return group_out(db, group)

    @app.delete("/groups/{group_id}/members/{user_id}", status_code=204)
    def remove_member(group_id: UUID, user_id: UUID, user=Depends(require_user), db=Depends(db_session)):
        group = db.get(Group, str(group_id))
        if not group or group.owner_id != user.id:
            raise HTTPException(404, "Owned group not found")
        if str(user_id) == group.owner_id:
            raise HTTPException(422, "Cannot remove group owner")
        db.execute(delete(Membership).where(Membership.group_id == str(group_id), Membership.user_id == str(user_id)))
        db.commit()
        return Response(status_code=204)

    @app.post("/objects", response_model=ObjectOut, status_code=201)
    def create_object(data: ObjectCreate, user=Depends(require_user), db=Depends(db_session)):
        obj = PhysicalObject(**data.model_dump(mode="json"), creator_id=user.id)
        db.add(obj)
        commit(db, "Marker already registered")
        return obj

    @app.get("/objects/by-marker/{marker_id}", response_model=ObjectOut)
    def by_marker(marker_id: UUID, db=Depends(db_session)):
        obj = db.scalar(select(PhysicalObject).where(PhysicalObject.marker_id == str(marker_id)))
        if not obj:
            raise HTTPException(404, "Object not found")
        return obj

    @app.get("/objects/{object_id}", response_model=ObjectOut)
    def read_object(object_id: UUID, db=Depends(db_session)):
        return get_object(db, object_id)

    @app.patch("/objects/{object_id}", response_model=ObjectOut)
    def patch_object(object_id: UUID, data: ObjectPatch, user=Depends(require_user), db=Depends(db_session)):
        obj = get_object(db, object_id)
        if obj.creator_id != user.id:
            raise HTTPException(403, "Only the creator can edit this object")
        changes = data.model_dump(exclude_unset=True)
        if (changes.get("latitude", obj.latitude) is None) != (changes.get("longitude", obj.longitude) is None):
            raise HTTPException(422, "Supply both latitude and longitude")
        for key, value in changes.items():
            setattr(obj, key, value)
        commit(db)
        return obj

    @app.post("/annotations", response_model=AnnotationOut, status_code=201)
    def create_annotation(data: AnnotationCreate, user=Depends(require_user), db=Depends(db_session)):
        get_object(db, data.object_id)
        if data.visibility == "group" and not member(db, data.group_id, user.id):
            raise HTTPException(403, "Group membership required")
        annotation = Annotation(**data.model_dump(mode="json"), author_id=user.id)
        db.add(annotation)
        commit(db)
        return serialize_annotation(db, annotation)

    @app.get("/objects/{object_id}/annotations", response_model=list[AnnotationOut])
    def list_annotations(object_id: UUID, user=Depends(optional_user), db=Depends(db_session),
                         limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0)):
        get_object(db, object_id)
        records = db.scalars(select(Annotation).where(Annotation.object_id == str(object_id), visibility_clause(user))
                            .order_by(Annotation.created_at, Annotation.id).offset(offset).limit(limit))
        return [serialize_annotation(db, a) for a in records]

    @app.get("/annotations/{annotation_id}", response_model=AnnotationOut)
    def read_annotation(annotation_id: UUID, user=Depends(optional_user), db=Depends(db_session)):
        return serialize_annotation(db, visible_annotation(db, annotation_id, user))

    @app.patch("/annotations/{annotation_id}", response_model=AnnotationOut)
    def patch_annotation(annotation_id: UUID, data: AnnotationPatch, user=Depends(require_user), db=Depends(db_session)):
        annotation = visible_annotation(db, annotation_id, user)
        if annotation.author_id != user.id:
            raise HTTPException(403, "Only the author can edit this annotation")
        changes = data.model_dump(exclude_unset=True, mode="json")
        visibility = changes.get("visibility", annotation.visibility)
        group_id = changes.get("group_id", annotation.group_id)
        if visibility != "group" and "group_id" not in changes:
            group_id = None
        if (visibility == "group") != (group_id is not None):
            raise HTTPException(422, "group_id is required only for group visibility")
        if visibility == "group" and not member(db, group_id, user.id):
            raise HTTPException(403, "Group membership required")
        changes["group_id"] = group_id
        for key, value in changes.items():
            setattr(annotation, key, value)
        commit(db)
        return serialize_annotation(db, annotation)

    @app.delete("/annotations/{annotation_id}", status_code=204)
    def delete_annotation(annotation_id: UUID, user=Depends(require_user), db=Depends(db_session)):
        annotation = visible_annotation(db, annotation_id, user)
        if annotation.author_id != user.id:
            raise HTTPException(403, "Only the author can delete this annotation")
        db.delete(annotation)
        db.commit()
        return Response(status_code=204)

    @app.get("/markers/{marker_id}.png", responses={200: {"content": {"image/png": {}}}}, response_class=Response)
    def marker_png(marker_id: UUID):
        image = qrcode.make("spatial:v1:" + str(marker_id), box_size=10, border=4)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png")

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    def companion():
        return FileResponse(static / "index.html")

    return app


app = create_app()
