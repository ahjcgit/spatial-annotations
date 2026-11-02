#!/usr/bin/env python3
"""Generate local printable markers. Nothing is registered or uploaded automatically."""
import argparse
import json
from pathlib import Path
from uuid import UUID, uuid4
import qrcode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--output", type=Path, default=Path("markers"))
    parser.add_argument("--marker-id", type=UUID, help="Regenerate a known marker (count must be 1)")
    args = parser.parse_args()
    if not 1 <= args.count <= 100 or (args.marker_id and args.count != 1):
        parser.error("count must be 1..100; use --count 1 with --marker-id")
    args.output.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(args.count):
        marker = str(args.marker_id or uuid4())
        payload = "spatial:v1:" + marker
        filename = marker + ".png"
        qrcode.make(payload, box_size=12, border=4).save(args.output / filename)
        records.append({"marker_id": marker, "payload": payload, "file": filename})
    manifest = args.output / "markers.json"
    if manifest.exists():
        records = json.loads(manifest.read_text()) + records
    manifest.write_text(json.dumps(records, indent=2) + "\n")
    cards = "".join(f'<article><img src="{r["file"]}" alt="Object marker"><h2>Object {i+1}</h2><p>{r["marker_id"]}</p></article>' for i, r in enumerate(records))
    (args.output / "print.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Object markers</title><style>article{break-inside:avoid;display:inline-block;margin:12mm;text-align:center;font:12px monospace}img{width:65mm;height:65mm}p{max-width:75mm;overflow-wrap:anywhere}</style>' + cards + '</html>')
    print(manifest)


if __name__ == "__main__":
    main()
