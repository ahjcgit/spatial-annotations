import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path}/test.db")) as client:
        yield client


@pytest.fixture
def users(client):
    result = {}
    for username in ("alice", "bob", "carol"):
        credentials = {"username": username, "password": "correct-horse-test"}
        user = client.post("/auth/register", json=credentials).json()
        token = client.post("/auth/login", json=credentials).json()["access_token"]
        result[username] = {"id": user["id"], "headers": {"Authorization": f"Bearer {token}"}}
    return result
