#!/usr/bin/env python3
"""Prepare an isolated Docker context from the verified input locks."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
context=ROOT/'.work/dependency-context'
if context.exists(): shutil.rmtree(context)
context.mkdir(parents=True,exist_ok=True)

def copy(src,dst):
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(src,dst,symlinks=True,copy_function=os.link)

for kind,names,suffix in [
    ('apt',['core','onnxruntime','openvino','python','runtime'],'apt'),
    ('wheels',['core','onnxruntime','openvino','python','tests'],'wheels')]:
    for name in names:
        target=context/kind/name
        target.mkdir(parents=True,exist_ok=True)
        for row in json.loads((ROOT/f'config/locks/{name}.{suffix}.json').read_text()):
            os.link(ROOT/'.work/inputs'/kind/name/row['filename'],target/row['filename'])
copy(ROOT/'config/locks',context/'locks')
copy(ROOT/'.work/sources/git',context/'sources/git')
selected=['server','backend','common','core','third_party','pytorch_backend','onnxruntime_backend','openvino_backend','python_backend','onnxruntime','openvino']
for name in selected:
    copy(ROOT/'.work/sources/checkouts'/name,context/'sources/checkouts'/name)
# Make Git URL rewriting independent of the host checkout path.
gitconfig=(ROOT/'.work/sources/gitconfig').read_text().replace(str(ROOT/'.work/sources'),'/opt/locked')
(context/'sources/gitconfig').write_text(gitconfig)
rows=json.loads((ROOT/'config/archives.lock.json').read_text())['archives']
cmake=context/'cmake';cmake.mkdir(exist_ok=True)
for environment in ['core','onnxruntime','openvino']:
    lines=[]
    for row in rows:
        if row['environment']!=environment or row['id'] in ['boost','tbb']:continue
        copy(ROOT/'.work/inputs/unpacked'/row['id'],context/'archives'/row['id'])
        # Core Googletest and OpenVINO Node headers have no upstream patches.
        if environment!='onnxruntime':
            lines.append(f'set(FETCHCONTENT_SOURCE_DIR_{row["name"].upper()} "/opt/locked/archives/{row["id"]}" CACHE PATH "Locked source" FORCE)')
    (cmake/(environment+'.cmake')).write_text('\n'.join(lines)+'\n')
for name in ['boost','tbb']:
    copy(ROOT/'.work/inputs/unpacked'/name,context/name)
    if name == "boost":
        target=context/"sources/boost.tar.gz"
        if target.exists(): target.unlink()
        row=next(r for r in rows if r["id"]=="boost")
        os.link(ROOT/".work/inputs/archives"/row["sha256"]/row["filename"],target)
# Keep ONNX Runtime's original download/extract/PATCH_COMMAND flow, but read
# the checksum-verified archives locally. No patches are skipped.
ort=context/'sources/checkouts/onnxruntime/cmake/deps.txt'
text=ort.read_text()
for row in rows:
    if row['environment']=='onnxruntime':
        # Archive files are copied alongside the extracted source directory.
        target=context/'sources/archives'/row['sha256']/row['filename']
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():target.unlink()
        os.link(ROOT/'.work/inputs/archives'/row['sha256']/row['filename'],target)
        text=text.replace(row['url'],f'file:///opt/locked/archives/{row["sha256"]}/{row["filename"]}')
# Break the hard link before applying this deliberate downstream substitution.
ort.unlink();ort.write_text(text)
shutil.copyfile(ROOT/'scripts/install-locked-debs.sh',context/'install-locked-debs.sh')
shutil.copyfile(ROOT/'Dockerfile.dependencies',context/'Dockerfile')
print(context)
