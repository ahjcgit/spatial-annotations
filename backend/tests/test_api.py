from datetime import timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import create_app
from app.models import User, SessionToken, utcnow


def make_object(client, users, **extra):
    response = client.post("/objects", headers=users["alice"]["headers"], json={"marker_id": str(uuid4()), "name": "White mug", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def make_annotation(client, users, obj, visibility="public", **extra):
    response = client.post("/annotations", headers=users["alice"]["headers"], json={"object_id": obj["id"], "content": f"{visibility} note", "visibility": visibility, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_authentication(client):
    credentials = {"username": "Alice", "password": "a secure password"}
    response = client.post("/auth/register", json=credentials)
    assert response.status_code == 201
    assert response.json()["username"] == "alice"
    assert "password" not in response.text
    assert response.json()["created_at"].endswith("Z")
    assert client.post("/auth/register", json=credentials).status_code == 409
    assert client.post("/auth/login", json={**credentials, "password": "wrong password"}).status_code == 401
    login = client.post("/auth/login", json=credentials).json()
    headers = {"Authorization": "Bearer " + login["access_token"]}
    assert client.get("/users/me", headers=headers).json()["username"] == "alice"
    assert client.get("/users/me").status_code == 401
    with client.app.state.session_factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        token = db.scalar(select(SessionToken))
        assert token.token_hash != login["access_token"]
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/users/me", headers=headers).status_code == 401


def test_expired_tokens(client, users):
    with client.app.state.session_factory() as db:
        token = db.scalar(select(SessionToken).where(SessionToken.user_id == users["bob"]["id"]))
        token.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/users/me", headers=users["bob"]["headers"]).status_code == 401
    assert client.get("/users/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_objects_unique_stable_identity_and_owner(client, users):
    obj = make_object(client, users, location_label="Lab", latitude=34.1, longitude=-118.1)
    other = make_object(client, users)
    assert obj["id"] != other["id"]
    assert client.post("/objects", headers=users["alice"]["headers"], json={"marker_id": obj["marker_id"]}).status_code == 409
    assert client.get("/objects/by-marker/" + obj["marker_id"]).json()["id"] == obj["id"]
    assert client.get("/objects/" + obj["id"]).json()["location_label"] == "Lab"
    assert client.get("/objects/by-marker/" + str(uuid4())).status_code == 404
    assert client.patch("/objects/" + obj["id"], headers=users["bob"]["headers"], json={"name": "stolen"}).status_code == 403
    assert client.patch("/objects/" + obj["id"], headers=users["alice"]["headers"], json={"name": "Mug A"}).json()["name"] == "Mug A"
    assert client.patch("/objects/" + obj["id"], headers=users["alice"]["headers"], json={"longitude": None}).status_code == 422


def test_end_to_end_sharing_and_revocation(client, users):
    """Two-user public/private/group workflow, including nonmember direct-ID probes."""
    alice, bob, carol = [users[u]["headers"] for u in ("alice", "bob", "carol")]
    obj = make_object(client, users)
    public = make_annotation(client, users, obj)
    private = make_annotation(client, users, obj, "private", content="ALICE_SECRET")
    group = client.post("/groups", headers=alice, json={"name": "Lab team"}).json()
    shared = make_annotation(client, users, obj, "group", group_id=group["id"], content="TEAM_SECRET")
    path = f'/objects/{obj["id"]}/annotations'
    assert {a["id"] for a in client.get(path, headers=alice).json()} == {public["id"], private["id"], shared["id"]}
    for headers in ({}, bob, carol):
        response = client.get(path, headers=headers)
        assert [a["id"] for a in response.json()] == [public["id"]]
        assert "SECRET" not in response.text
        for hidden in (private, shared):
            assert client.get("/annotations/" + hidden["id"], headers=headers).status_code == 404
    assert client.post(f'/groups/{group["id"]}/members', headers=bob, json={"username": "bob"}).status_code == 404
    assert client.get("/groups", headers=bob).json() == []
    assert client.post(f'/groups/{group["id"]}/members', headers=alice, json={"username": "bob"}).status_code == 200
    assert {a["id"] for a in client.get(path, headers=bob).json()} == {public["id"], shared["id"]}
    assert client.get("/annotations/" + shared["id"], headers=bob).status_code == 200
    assert client.delete(f'/groups/{group["id"]}/members/{users["bob"]["id"]}', headers=alice).status_code == 204
    assert client.get("/annotations/" + shared["id"], headers=bob).status_code == 404
    assert [a["id"] for a in client.get(path, headers=bob).json()] == [public["id"]]
    # Public object metadata includes neither annotations nor a hidden-content count.
    assert "SECRET" not in client.get("/objects/" + obj["id"]).text
    assert "annotations" not in client.get("/objects/" + obj["id"]).json()


@pytest.mark.parametrize("visibility", ["public", "private", "group"])
def test_author_only_mutation(client, users, visibility):
    obj = make_object(client, users)
    extra = {}
    if visibility == "group":
        group = client.post("/groups", headers=users["alice"]["headers"], json={"name": "team"}).json()
        extra["group_id"] = group["id"]
        client.post(f'/groups/{group["id"]}/members', headers=users["alice"]["headers"], json={"username": "bob"})
    annotation = make_annotation(client, users, obj, visibility, **extra)
    path = "/annotations/" + annotation["id"]
    for method, body in (("PATCH", {"content": "unauthorized"}), ("DELETE", None)):
        response = client.request(method, path, headers=users["bob"]["headers"], json=body)
        assert response.status_code == (404 if visibility == "private" else 403)
        assert client.request(method, path, json=body).status_code == 401
    changed = client.patch(path, headers=users["alice"]["headers"], json={"content": "Updated", "visibility": "private"})
    assert changed.status_code == 200
    assert changed.json()["group_id"] is None
    assert changed.json()["updated_at"] >= annotation["updated_at"]
    assert client.get(path, headers=users["bob"]["headers"]).status_code == 404
    assert client.delete(path, headers=users["alice"]["headers"]).status_code == 204
    assert client.get(path, headers=users["alice"]["headers"]).status_code == 404


@pytest.mark.parametrize("data", [
    {"content": ""}, {"content": "   "}, {"visibility": "invalid"},
    {"visibility": "group"}, {"group_id": str(uuid4())}, {"content": "x" * 10001},
    {"author_id": str(uuid4())}, {"created_at": "2000-01-01"}, {"object_id": "invalid"},
])
def test_invalid_annotations(client, users, data):
    obj = make_object(client, users)
    response = client.post("/annotations", headers=users["alice"]["headers"], json={"object_id": obj["id"], "content": "ok", **data})
    assert response.status_code == 422
    assert '"input"' not in response.text


def test_invalid_requests_and_group_injection(client, users):
    obj = make_object(client, users)
    headers = users["alice"]["headers"]
    assert client.post("/objects", json={"marker_id": str(uuid4())}).status_code == 401
    assert client.post("/objects", headers=headers, json={"marker_id": str(uuid4()), "latitude": 91, "longitude": 1}).status_code == 422
    assert client.post("/objects", headers=headers, json={"marker_id": str(uuid4()), "latitude": 1}).status_code == 422
    assert client.post("/annotations", headers=headers, json={"object_id": obj["id"], "content": "secret", "visibility": "group", "group_id": str(uuid4())}).status_code == 403
    a = make_annotation(client, users, obj)
    for patch in ({"content": None}, {"visibility": None}, {"author_id": users["bob"]["id"]}, {"visibility": "group"}):
        assert client.patch("/annotations/" + a["id"], headers=headers, json=patch).status_code == 422
    assert client.patch("/annotations/" + a["id"], headers=headers, json={"visibility": "group", "group_id": str(uuid4())}).status_code == 403
    assert client.post("/auth/register", json={"username": "eve", "password": "TOOSHORT"}).status_code == 422
    assert "TOOSHORT" not in client.post("/auth/register", json={"username": "eve", "password": "TOOSHORT"}).text


def test_pagination_only_counts_visible(client, users):
    obj = make_object(client, users)
    make_annotation(client, users, obj, "private")
    a = make_annotation(client, users, obj)
    b = make_annotation(client, users, obj)
    path = f'/objects/{obj["id"]}/annotations'
    assert client.get(path + "?limit=1").json()[0]["id"] == a["id"]
    assert client.get(path + "?limit=1&offset=1").json()[0]["id"] == b["id"]
    assert client.get(path + "?limit=101").status_code == 422


def test_persistence_across_app_restart(tmp_path):
    url = f"sqlite:///{tmp_path}/persistent.db"
    with TestClient(create_app(url)) as client:
        credentials = {"username": "alice", "password": "persistent password"}
        client.post("/auth/register", json=credentials)
        headers = {"Authorization": "Bearer " + client.post("/auth/login", json=credentials).json()["access_token"]}
        obj = client.post("/objects", headers=headers, json={"marker_id": str(uuid4())}).json()
        annotation = client.post("/annotations", headers=headers, json={"object_id": obj["id"], "content": "Survives restart", "visibility": "public"}).json()
    with TestClient(create_app(url)) as client:
        assert client.get("/annotations/" + annotation["id"]).json()["content"] == "Survives restart"
        assert client.get("/users/me", headers=headers).status_code == 200


def test_companion_and_marker(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200
    marker = client.get(f"/markers/{uuid4()}.png")
    assert marker.status_code == 200
    assert marker.content.startswith(b"\x89PNG")
    assert client.get("/openapi.json").status_code == 200


def test_identical_names_different_markers_never_share_notes(client, users):
    a = make_object(client, users, name="Identical mug")
    b = make_object(client, users, name="Identical mug")
    note_a = make_annotation(client, users, a, content="Only A")
    note_b = make_annotation(client, users, b, content="Only B")
    for obj, expected in ((a, note_a), (b, note_b), (a, note_a)):
        resolved = client.get('/objects/by-marker/' + obj['marker_id']).json()
        assert resolved['id'] == obj['id']
        assert [n['id'] for n in client.get('/objects/' + resolved['id'] + '/annotations').json()] == [expected['id']]
    assert client.get('/objects/by-marker/not-a-uuid').status_code == 422
    assert client.get('/objects/' + str(uuid4()) + '/annotations').status_code == 404


def test_group_revocation_and_private_data_persist_across_restart(tmp_path):
    url = f"sqlite:///{tmp_path}/sharing.db"
    with TestClient(create_app(url)) as client:
        auth = {}
        for name in ('alice', 'bob'):
            credentials = dict(username=name, password='persistent secure password')
            client.post('/auth/register', json=credentials).raise_for_status()
            auth[name] = {'Authorization': 'Bearer ' + client.post('/auth/login', json=credentials).json()['access_token']}
        obj = client.post('/objects', headers=auth['alice'], json={'marker_id': str(uuid4())}).json()
        group = client.post('/groups', headers=auth['alice'], json={'name': 'team'}).json()
        bob = client.get('/users/me', headers=auth['bob']).json()
        client.post('/groups/' + group['id'] + '/members', headers=auth['alice'], json={'username': 'bob'}).raise_for_status()
        for visibility in ('public','private','group'):
            client.post('/annotations', headers=auth['alice'], json=dict(object_id=obj['id'], content=visibility,
                visibility=visibility, group_id=group['id'] if visibility=='group' else None)).raise_for_status()
        client.delete('/groups/' + group['id'] + '/members/' + bob['id'], headers=auth['alice']).raise_for_status()
    with TestClient(create_app(url)) as client:
        assert client.get('/objects/by-marker/' + obj['marker_id']).json()['id'] == obj['id']
        path = '/objects/' + obj['id'] + '/annotations'
        assert {n['visibility'] for n in client.get(path, headers=auth['alice']).json()} == {'public','private','group'}
        assert [n['visibility'] for n in client.get(path, headers=auth['bob']).json()] == ['public']
