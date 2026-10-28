#!/usr/bin/env python3
"""Prevent --reuse-artifacts from bypassing input locks."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from dependencies import ROOT, lock_id

h=hashlib.sha256(lock_id().encode())
for p in sorted(list((ROOT/'scripts').glob('*.sh'))+list((ROOT/'scripts').glob('lock-*.py'))+[ROOT/'config/build.env',ROOT/'Dockerfile.python']):
    h.update(p.name.encode()+b'\0'+p.read_bytes())
fingerprint=h.hexdigest()
images={n:subprocess.check_output(['docker','image','inspect',n,'--format','{{.Id}}'],text=True).strip() for n in ['tritonserver:latest','tritonserver_buildbase:latest']}
path=ROOT/'.work/core-build-receipt.json'
expected=dict(fingerprint=fingerprint,images=images)
if sys.argv[1]=='write':
    path.write_text(json.dumps(expected,indent=2)+'\n')
elif not path.exists() or json.loads(path.read_text())!=expected:
    sys.exit('Cached core/framework images do not match this build lock. Run ./triton build first.')
