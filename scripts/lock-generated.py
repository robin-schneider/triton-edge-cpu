#!/usr/bin/env python3
"""Constrain the pinned NVIDIA generator to local sources and offline builds."""
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
source=root/'.work/server'
generated=source/'build'
sys.path.insert(0,str(root/'scripts'))
from dependencies import IMAGES,lock_id

def dep(name):return 'local/triton-deps-'+name+':'+lock_id()
epoch=subprocess.check_output(['git','-C',str(source),'show','-s','--format=%ct','HEAD'],text=True).strip()
work=source/'.cpu-build';work.mkdir(exist_ok=True)
for name in ['lock-backend.py','lock-framework.py']:
    shutil.copyfile(root/'scripts'/name,work/name)
shutil.copyfile(root/'patches/openvino-cpu-only.patch',work/'openvino-cpu-only.patch')
# The dependency image contains packages and freshly acquired sources only.
(generated/'Dockerfile.buildbase').write_text(f'''FROM {dep('core')}
ENV SOURCE_DATE_EPOCH={epoch} \\
    LOCK_ONNXRUNTIME_IMAGE={dep('onnxruntime')} \\
    LOCK_OPENVINO_IMAGE={dep('openvino')} \\
    LOCK_OPENVINO_BUILD_NUMBER={os.environ['OPENVINO_BUILD_NUMBER']} \\
    LOCK_ONNXRUNTIME_BRANCH={os.environ['ONNXRUNTIME_BUILD_BRANCH']} \\
    LOCK_ONNXRUNTIME_ABBREV={os.environ['ONNXRUNTIME_BUILD_ABBREV']} \\
    CLEAN_BUILD={os.environ.get('CLEAN_BUILD','0')}
WORKDIR /workspace
COPY . .
ENTRYPOINT []
''')
cmake=(generated/'cmake_build').read_text()
for name in ['pytorch','onnxruntime','openvino']:
    repository=name+'_backend'
    pattern=rf'git clone [^\n;]+https://github.com/triton-inference-server/{repository}\.git {name}; git --git-dir {name}/\.git log --oneline -1'
    replacement=f'cp -a /opt/locked/checkouts/{repository} {name}; '
    if name=='openvino': replacement+='git -C openvino apply /workspace/.cpu-build/openvino-cpu-only.patch; '
    replacement+=f'python3 /workspace/.cpu-build/lock-backend.py {name}'
    cmake,count=re.subn(pattern,replacement,cmake)
    if count!=1:raise ValueError('Unexpected clone recipe for '+name)
(generated/'cmake_build').write_text(cmake)
# Preserve runtime COPY/ELF fixups from the upstream recipe. Package contents
# are already locked in the dependency stage; no wheel extras are resolved.
path=generated/'Dockerfile'
blocks=[]
for line in path.read_text().splitlines(keepends=True):
    if blocks and blocks[-1].rstrip().endswith('\\'):blocks[-1]+=line
    else:blocks.append(line)
text=''.join(b for b in blocks if not (b.startswith('RUN ') and any(x in b for x in ['apt-get','pip3 install','pip install'])))
text=text.replace('ARG BASE_IMAGE=ubuntu:24.04','ARG BASE_IMAGE='+dep('python'))
pos=re.search(r'(?m)^FROM ',text).start()
text=text[:pos]+'FROM '+dep('core')+' AS locked_tools\n'+text[pos:]
text=text.replace('FROM ${BASE_IMAGE}\n','FROM ${BASE_IMAGE}\nCOPY --from=locked_tools /usr/local/bin/patchelf /usr/local/bin/patchelf\n',1)
# The upstream generator has already been given the digest-pinned NGC image.
if re.search(r'(?m)^RUN .*\b(apt-get|pip3? install|wget|curl)\b',text):
    raise ValueError('Unreviewed runtime dependency download')
text+='\nRUN python3 -m pip install --no-index --no-deps /opt/tritonserver/python/tritonserver-*.whl /opt/tritonserver/python/tritonfrontend-*.whl\n'
path.write_text(text)
path=generated/'docker_build';text=path.read_text()
text=text.replace('docker build ', 'docker build --network=none '+('--no-cache ' if os.environ.get('CLEAN_BUILD')=='1' else ''))
text=text.replace(' --pull ', ' --pull=false ')
text=text.replace('docker run ', 'docker run --network=none ')
text=text.replace('tritonserver_builder','tritonserver_locked_builder')
path.write_text(text)
print('Generated recipes consume locked local inputs with network disabled.')
