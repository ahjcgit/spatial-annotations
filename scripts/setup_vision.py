#!/usr/bin/env python3
"""Download verified model weights and optionally a CC0 test photo from official sources."""
import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
REVISION='48b10fa505aeb51fbd127fc60a5c660040e823b7'
SHA256='4b82da9944b88577175ee23a459dce2e26e6e4be573def65b1055dc2d9720186'


def fetch_verified(url,path,checksum,limit):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:
        with urlopen(url,timeout=60) as response: content=response.read(limit+1)
        if len(content)>limit or hashlib.sha256(content).hexdigest()!=checksum:
            raise RuntimeError('Download checksum mismatch; refusing to install '+path.name)
        temporary=path.with_suffix(path.suffix+'.download');temporary.write_bytes(content);temporary.replace(path)
    print(f'Verified {path} SHA256 {checksum}')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sample',action='store_true',help='Also fetch Rachel Michetti’s CC0 coffee photo from scikit-image');a=p.parse_args()
    fetch_verified('https://huggingface.co/opencv/object_detection_nanodet/resolve/main/object_detection_nanodet_2022nov.onnx',ROOT/'artifacts/models/nanodet.onnx',SHA256,4_000_000)
    if a.sample:
        fetch_verified('https://raw.githubusercontent.com/scikit-image/scikit-image/v0.19.3/skimage/data/coffee.png',ROOT/'artifacts/vision/coffee.png','cc02f8ca188b167c775a7101b5d767d1e71792cf762c33d6fa15a4599b5a8de7',1_000_000)

if __name__=='__main__': main()
