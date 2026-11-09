#!/usr/bin/env python3
"""Create an isolated sanitizer presentation fixture from an existing demo account file."""
import argparse
import json
import os
import uuid
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True, help='Existing scripts/demo.py dataset')
    parser.add_argument('--output', type=Path, default=Path('hardware-runs/rayneo/presentation-data.json'))
    args = parser.parse_args()
    if args.output.exists():
        prepared = json.loads(args.output.read_text())
        if prepared.get('target') != 'bottle' or len(prepared.get('objects', [])) != 2:
            parser.error('Output exists but is not a bottle presentation fixture; choose a new output path')
        print(f'Reusing existing presentation fixture: {args.output}')
        return
    data = json.loads(args.data.read_text())
    alice = data['users'][0]
    with httpx.Client(base_url=data['backend'], timeout=20) as client:
        login = client.post('/auth/login', json={key: alice[key] for key in ('username', 'password')})
        login.raise_for_status()
        headers = {'Authorization': 'Bearer ' + login.json()['access_token']}
        try:
            objects = []
            for name in ('Hand sanitizer', 'Other bottle'):
                response = client.post('/objects', headers=headers, json={
                    'marker_id': str(uuid.uuid4()), 'name': name,
                    'spatial_metadata': {'detection_label': 'bottle'}})
                response.raise_for_status()
                objects.append(response.json())
            notes = {}
            for visibility, content in (
                ('public', 'Hand sanitizer — on the demo table.'),
                ('private', 'Private reminder: check the refill supply.'),
                ('group', 'Team note: return this bottle to the demo table after use.'),
            ):
                response = client.post('/annotations', headers=headers, json={
                    'object_id': objects[0]['id'], 'content': content, 'visibility': visibility,
                    'group_id': data['group_id'] if visibility == 'group' else None})
                response.raise_for_status()
                notes[visibility] = response.json()
            data.update(target='bottle', objects=objects, annotations=notes)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as output:
                json.dump(data, output, indent=2)
                output.write('\n')
        finally:
            client.post('/auth/logout', headers=headers).raise_for_status()
    print(f'Prepared sanitizer presentation: {args.output}')


if __name__ == '__main__':
    main()
