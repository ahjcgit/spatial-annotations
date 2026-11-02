#!/usr/bin/env python3
"""Run a real HTTP two-user demo against a running backend; leaves uniquely named demo data."""
import argparse
import json
import secrets
from pathlib import Path
from uuid import uuid4
import httpx


def run(url, output):
    suffix = uuid4().hex[:10]
    with httpx.Client(base_url=url.rstrip('/'), timeout=20) as client:
        def request(method, path, token=None, data=None, expected=200):
            response = client.request(method, path, headers={"Authorization": "Bearer " + token} if token else {}, json=data)
            assert response.status_code == expected, f"{method} {path}: {response.status_code} {response.text}"
            return response.json() if response.content else None
        users = []
        for name in ("alice", "bob"):
            credentials = {"username": name + "_" + suffix, "password": secrets.token_urlsafe(18)}
            user = request("POST", "/auth/register", data=credentials, expected=201)
            login = request("POST", "/auth/login", data=credentials)
            users.append({**credentials, "id": user["id"], "token": login["access_token"]})
        a, b = users
        objects = [request("POST", "/objects", a["token"], {"marker_id": str(uuid4()), "name": f"Identical mug {n}", "location_label": "Demo table"}, 201) for n in ("A", "B")]
        obj = objects[0]
        group = request("POST", "/groups", a["token"], {"name": "Demo team " + suffix}, 201)
        notes = {}
        for visibility in ("public", "private", "group"):
            notes[visibility] = request("POST", "/annotations", a["token"], {"object_id": obj["id"], "content": f"{visibility} note on mug A", "visibility": visibility, "group_id": group["id"] if visibility == "group" else None}, 201)
        path = f'/objects/{obj["id"]}/annotations'
        assert [n["visibility"] for n in request("GET", path, b["token"])] == ["public"]
        request("GET", '/annotations/' + notes['private']['id'], b['token'], expected=404)
        request("GET", '/annotations/' + notes['group']['id'], b['token'], expected=404)
        request("POST", f'/groups/{group["id"]}/members', a["token"], {"username": b["username"]})
        assert {n["visibility"] for n in request("GET", path, b["token"])} == {"public", "group"}
        assert request("GET", f'/objects/{objects[1]["id"]}/annotations', b["token"]) == []
        request("PATCH", '/annotations/' + notes['public']['id'], b['token'], {"content": "unauthorized"}, 403)
        request("DELETE", '/annotations/' + notes['public']['id'], b['token'], expected=403)
        request("DELETE", f'/groups/{group["id"]}/members/{b["id"]}', a["token"], expected=204)
        request("GET", '/annotations/' + notes['group']['id'], b['token'], expected=404)
        # Restore membership for the subsequent physical demo.
        request("POST", f'/groups/{group["id"]}/members', a["token"], {"username": b["username"]})
        result = {"backend": url, "users": [{k:v for k,v in u.items() if k != "token"} for u in users], "objects": objects, "group_id": group["id"], "annotations": notes}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
        output.chmod(0o600)
        print("PASS: HTTP registration, two objects, public/private/group isolation, author-only mutations, membership revocation.")
        print(f"Demo credentials and IDs saved locally to {output}; do not commit this file.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, default=Path("demo-data.json"))
    args = parser.parse_args()
    run(args.url, args.output)
