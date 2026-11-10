#!/usr/bin/env python3
"""Put a generated QR image in an emulator virtual camera scene. This is NOT a webcam or RayNeo test."""
import argparse
from pathlib import Path
import socket
import subprocess


def set_scene(serial, image, container=None, token_file=None):
    if not serial.startswith('emulator-'): raise ValueError('Virtual scene requires an emulator serial')
    port=int(serial.split('-')[1])
    if container:
        token=subprocess.check_output(['docker','exec',container,'cat','/root/.emulator_console_auth_token']).decode().strip()
        target='/tmp/spatial-scene-'+image.name
        subprocess.run(['docker','cp',str(image.resolve()),container+':'+target],check=True,stdout=subprocess.DEVNULL)
    else:
        token=(token_file or Path.home()/'.emulator_console_auth_token').read_text().strip()
        target=str(image.resolve())
    if '\n' in target or '\r' in target: raise ValueError('Invalid image path')
    with socket.create_connection(('127.0.0.1',port),timeout=5) as connection:
        def read():
            result=b''
            while not (result.endswith(b'OK\r\n') or b'KO:' in result):
                chunk=connection.recv(4096)
                if not chunk: raise RuntimeError('Emulator console closed')
                result+=chunk
            if b'KO:' in result: raise RuntimeError('Emulator console rejected scene command')
        read()
        connection.sendall(('auth '+token+'\n').encode());read()
        for location in ('wall','table'):
            connection.sendall(f'virtualscene-image {location} {target}\n'.encode());read()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--serial',default='emulator-5554')
    p.add_argument('--image',type=Path,required=True);p.add_argument('--container');p.add_argument('--token-file',type=Path)
    a=p.parse_args();set_scene(a.serial,a.image,a.container,a.token_file)
    print('Generated image loaded into emulator virtual scene; not a physical-camera test.')
