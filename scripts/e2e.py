#!/usr/bin/env python3
"""Run a real HTTP two-user demo against a running backend; leaves uniquely named demo data."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
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
        objects = [request("POST", "/objects", a["token"], {"marker_id": str(uuid4()), "name": f"Mug {n}", "location_label": "Demo table"}, 201) for n in ("A", "B")]
        for registered in objects:
            assert request("GET", "/objects/by-marker/" + registered["marker_id"])["id"] == registered["id"]
        request("GET", "/objects/by-marker/not-a-uuid", expected=422)
        request("GET", "/objects/by-marker/" + str(uuid4()), expected=404)
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
        assert [n["visibility"] for n in request("GET", path, b["token"])] == ["public"]
        assert {n["visibility"] for n in request("GET", path, a["token"])} == {"public", "private", "group"}
        assert [n["visibility"] for n in request("GET", path)] == ["public"]
        changed = request("PATCH", '/annotations/' + notes['public']['id'], a['token'], {"content": "public note on mug A · update verified"})
        notes['public'] = changed
        assert request("GET", path, b['token'])[0]['content'] == changed['content']
        # Restore membership for the subsequent physical demo.
        request("POST", f'/groups/{group["id"]}/members', a["token"], {"username": b["username"]})
        result = {"backend": url, "users": [{k:v for k,v in u.items() if k != "token"} for u in users], "objects": objects, "group_id": group["id"], "annotations": notes}
        output.parent.mkdir(parents=True, exist_ok=True)
        # Secure permissions from creation, rather than after writing credentials.
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream: stream.write(json.dumps(result, indent=2) + "\n")
        print("PASS: HTTP registration, two objects, public/private/group isolation, author-only mutations, membership revocation.")
        print(f"Demo credentials and IDs saved locally to {output}; do not commit this file.")



def verify(url, data_path, evidence):
    """Read-only data verification (login creates sessions); also usable after a server restart."""
    data = json.loads(data_path.read_text())
    records = []
    with httpx.Client(base_url=url.rstrip('/'), timeout=20) as client:
        for user in data['users']:
            login = client.post('/auth/login', json={key:user[key] for key in ('username','password')})
            login.raise_for_status()
            headers = {'Authorization':'Bearer '+login.json()['access_token']}
            try:
                for repeat in range(5):
                    for index, obj in enumerate(data['objects']):
                        started = time.monotonic_ns()
                        resolved = client.get('/objects/by-marker/'+obj['marker_id'], headers=headers)
                        resolved.raise_for_status()
                        assert resolved.json()['id'] == obj['id']
                        response = client.get('/objects/'+resolved.json()['id']+'/annotations',headers=headers)
                        response.raise_for_status(); notes = response.json()
                        assert all(note['object_id'] == obj['id'] for note in notes)
                        expected = {data['annotations'][v]['id'] for v in ('public','private','group') if v != 'private' or user == data['users'][0]} if index == 0 else set()
                        assert expected.issubset({n['id'] for n in notes})
                        if user == data['users'][1]: assert data['annotations']['private']['id'] not in {n['id'] for n in notes}
                        if index == 1: assert not {n['id'] for n in data['annotations'].values()} & {n['id'] for n in notes}
                        elapsed = (time.monotonic_ns()-started)/1_000_000
                        records.append(dict(test_id=str(uuid4()),timestamp=datetime.now(timezone.utc).isoformat(),
                            environment='desktop_http',identification_method='simulated_lookup',marker_uuid=obj['marker_id'],
                            recognition_success=None,recognition_latency_ms=None,backend_success=True,
                            backend_latency_ms=elapsed,total_latency_ms=elapsed,annotation_count=len(notes),failure_category=None))
            finally:
                client.post('/auth/logout',headers=headers).raise_for_status()
    evidence.parent.mkdir(parents=True,exist_ok=True)
    evidence.write_text(''.join(json.dumps(row)+'\n' for row in records))
    print(f'PASS: {len(records)} repeated marker → object → authorized annotation HTTP lookups; {evidence}')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, default=Path("demo-data.json"))
    parser.add_argument("--verify", action="store_true", help="Verify existing output dataset, including after restart")
    parser.add_argument("--evidence", type=Path, default=Path("artifacts/http-results.jsonl"))
    args = parser.parse_args()
    if args.verify: verify(args.url, args.output, args.evidence)
    else: run(args.url, args.output)
