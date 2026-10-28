#!/usr/bin/env python3
"""Read immutable OCI inputs and name locally built dependency stages."""
import hashlib
import json
from pathlib import Path
import re
import sys
import subprocess

ROOT=Path(__file__).resolve().parents[1]
IMAGES=json.loads((ROOT/'config/images.lock.json').read_text())['images']
for name,image in IMAGES.items():
    if not re.fullmatch(r'(docker\.io|nvcr\.io)/[\w./-]+:[\w.+-]+@sha256:[0-9a-f]{64}',image):
        raise ValueError('Unapproved registry or unpinned image: '+image)

def lock_id():
    h=hashlib.sha256()
    files=list((ROOT/'config/locks').glob('*'))+list((ROOT/'config').glob('*.lock.json'))
    files += [ROOT/'Dockerfile.dependencies',ROOT/'scripts/dependency-context.py',ROOT/'scripts/install-locked-debs.sh']
    for path in sorted(files):
        h.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes()+b'\0')
    return h.hexdigest()[:20]


def image_id(name):
    return subprocess.check_output(['docker','image','inspect',
        'local/triton-deps-'+name+':'+lock_id(),'--format','{{.Id}}'],
        text=True,stderr=subprocess.DEVNULL).strip()

def receipt(action,name):
    path=ROOT/'.work/dependency-receipts.json'
    records=json.loads(path.read_text()) if path.exists() else {}
    key=lock_id()+':'+name
    if action=='cached':
        try: actual=image_id(name)
        except subprocess.CalledProcessError: sys.exit(1)
        sys.exit(0 if records.get(key)==actual else 1)
    records[key]=image_id(name)
    path.write_text(json.dumps(records,indent=2)+'\n')

if __name__=='__main__':
    cmd=sys.argv[1]
    if cmd in ['cached','record']: receipt(cmd,sys.argv[2])
    elif cmd=='image': print(IMAGES[sys.argv[2]])
    elif cmd=='tag': print('local/triton-deps-'+sys.argv[2]+':'+lock_id())
    elif cmd=='id': print(lock_id())
    elif cmd=='check': print(f'{len(IMAGES)} digest-pinned OCI inputs; registries: docker.io, nvcr.io')
    else: raise ValueError(cmd)
