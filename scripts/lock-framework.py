"""Executed after NVIDIA's pinned framework generator has written its recipe."""
from pathlib import Path
import os
import re
import shlex

path=Path(output)  # supplied by runpy from the original pinned generator
text=path.read_text()
lines=text.splitlines(keepends=True)
blocks=[]
for line in lines:
    if blocks and blocks[-1].rstrip().endswith('\\'):
        blocks[-1]+=line
    else:
        blocks.append(line)
result=[]
clones=0
for block in blocks:
    if block.startswith('FROM '):
        block='FROM '+os.environ['LOCK_'+environment.upper()+'_IMAGE']+'\n'
    if block.startswith('RUN ') and any(s in block for s in ['apt-get','pip3 install','pip install']):
        continue
    if block.startswith('RUN git clone '):
        clones+=1
        block=f'RUN cp -a /opt/locked/checkouts/{environment} /workspace/{environment}\n'
        if environment=='onnxruntime':
            block=block.rstrip()+' && git -C /workspace/onnxruntime checkout -B '+shlex.quote(os.environ['LOCK_ONNXRUNTIME_BRANCH'])+' && git -C /workspace/onnxruntime config core.abbrev '+shlex.quote(os.environ['LOCK_ONNXRUNTIME_ABBREV'])+'\n'

    if environment=='openvino' and block.startswith('RUN cmake ') and not block.startswith('RUN cmake --build '):
        block=block.replace('RUN cmake ', 'RUN cmake -DCMAKE_TOOLCHAIN_FILE=/opt/locked/openvino.cmake ',1)
    result.append(block)
if clones!=1:
    raise ValueError('Unexpected source acquisition recipe: '+str(clones))
text=''.join(result)
if re.search(r'(?m)^RUN .*\b(git (clone|fetch)|apt-get|pip3? install|wget|curl)\b',text):
    raise ValueError('Unreviewed download in framework recipe')
# Forward the same reproducible timestamp into nested framework builds.
text=text.replace('FROM '+os.environ['LOCK_'+environment.upper()+'_IMAGE']+'\n',
                  'FROM '+os.environ['LOCK_'+environment.upper()+'_IMAGE']+'\n'+
                  'ENV SOURCE_DATE_EPOCH='+os.environ['SOURCE_DATE_EPOCH']+'\n',1)
if environment=='openvino':
    text=text.replace('ENV SOURCE_DATE_EPOCH=', 'ENV CI_BUILD_NUMBER='+os.environ['LOCK_OPENVINO_BUILD_NUMBER']+'\nENV SOURCE_DATE_EPOCH=',1)
path.write_text(text)
