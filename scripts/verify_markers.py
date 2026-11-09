#!/usr/bin/env python3
"""Add exact printable and backend-served PNGs to the production Kotlin replay manifest."""
import argparse
import io
import json
from pathlib import Path
import httpx
from PIL import Image
from qr_frames import save_frame


def main():
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True)
    p.add_argument('--markers',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();data=json.loads(a.data.read_text());manifest=a.output/'manifest.json'
    records=json.loads(manifest.read_text()) if manifest.exists() else []
    with httpx.Client(base_url=data['backend'],timeout=10) as client:
        for obj in data['objects']:
            marker=obj['marker_id'];name=obj['name'].replace(' ','-')
            response=client.get('/markers/'+marker+'.png');response.raise_for_status()
            for method,image in [('print',Image.open(a.markers/(marker+'.png'))),('backend',Image.open(io.BytesIO(response.content)))]:
                records.append(save_frame(a.output,image,method+'-'+name,marker,method+'_marker_png_jvm'))
    records=list({r['file']:r for r in records}.values())
    manifest.write_text(json.dumps(records,indent=2)+'\n')
    print('Exact printable and backend PNG bytes prepared; decoding is verified by Android ReplayTest, not this script.')

if __name__=='__main__':main()
