#!/usr/bin/env python3
"""Package a runtime filesystem into a deterministic, locally loaded Docker image.

Compiler/dependency images retain build caching. Only the deployable image is
flattened; its provenance and generated recipes are kept in artifacts/.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

from dependencies import ROOT, lock_id


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def omitted(name):
    return name.startswith(('var/log/', 'var/cache/', 'tmp/')) or name in {
        'var/lib/systemd/random-seed', 'var/lib/urandom/random-seed'}


def stable_contents(name, contents, epoch):
    if name in {'etc/machine-id', 'var/lib/dbus/machine-id'}:
        return b''
    if name in {'etc/shadow', 'etc/shadow-'}:
        result=[]
        for line in contents.decode().splitlines():
            fields=line.split(':')
            if len(fields)>2 and fields[2].isdigit():
                fields[2]=str(epoch//86400)
            result.append(':'.join(fields))
        return ('\n'.join(result)+'\n').encode()
    return contents


def canonical_layer(source, destination, epoch):
    with tarfile.open(source, 'r:') as src, tarfile.open(destination, 'w:', format=tarfile.PAX_FORMAT) as dst:
        members={m.name.removeprefix('./').rstrip('/'):m for m in src.getmembers()}
        names=sorted(n for n in members if n and not omitted(n))
        # Hard links must follow their targets, regardless of export ordering.
        names.sort(key=lambda n:(members[n].islnk(),n))
        for name in names:
            original=members[name]
            member=copy.copy(original)
            member.name=name
            member.mtime=epoch
            member.uname=member.gname=''
            member.pax_headers={}
            if member.islnk():
                target=member.linkname.removeprefix('./').lstrip('/')
                seen=set()
                while target in members and members[target].islnk():
                    if target in seen:
                        raise ValueError('Cyclic hard link: '+name)
                    seen.add(target)
                    target=members[target].linkname.removeprefix('./').lstrip('/')
                if omitted(target):
                    raise ValueError('Hard link references omitted runtime data: '+target)
                member.linkname=target
            if member.isfile():
                if name in {'etc/machine-id','var/lib/dbus/machine-id','etc/shadow','etc/shadow-'}:
                    data=stable_contents(name,src.extractfile(original).read(),epoch)
                    member.size=len(data)
                    dst.addfile(member,io.BytesIO(data))
                else:
                    dst.addfile(member,src.extractfile(original))
            else:
                dst.addfile(member)


def add_bytes(archive,name,data,epoch):
    info=tarfile.TarInfo(name)
    info.size=len(data)
    info.mode=0o644
    info.mtime=epoch
    archive.addfile(info,io.BytesIO(data))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('target')
    parser.add_argument('--epoch',type=int,required=True)
    args=parser.parse_args()
    image=json.loads(run('docker','image','inspect',args.source))[0]
    if (image['Os'],image['Architecture'])!=('linux','amd64'):
        raise ValueError('Expected a Linux amd64 runtime')
    config=copy.deepcopy(image['Config'])
    config.setdefault('Labels',{}).update({
        'io.triton-cpu.input-lock':lock_id(),
        'io.triton-cpu.packaging':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    created=datetime.fromtimestamp(args.epoch,timezone.utc).isoformat().replace('+00:00','Z')
    work=ROOT/'.work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='normalize-',dir=work) as folder:
        folder=Path(folder)
        container=run('docker','create','--network','none','--entrypoint','/bin/true',args.source)
        try:
            subprocess.run(['docker','export','--output',str(folder/'export.tar'),container],check=True)
        finally:
            subprocess.run(['docker','rm',container],check=True,stdout=subprocess.DEVNULL)
        layer=folder/'layer.tar'
        canonical_layer(folder/'export.tar',layer,args.epoch)
        (folder/'export.tar').unlink()
        config_json=dict(created=created,architecture='amd64',os='linux',config=config,
                         rootfs=dict(type='layers',diff_ids=['sha256:'+digest(layer)]),
                         history=[dict(created=created,created_by='triton locked runtime packaging')])
        config_bytes=json.dumps(config_json,sort_keys=True,separators=(',',':')).encode()
        config_name=hashlib.sha256(config_bytes).hexdigest()+'.json'
        manifest=json.dumps([dict(Config=config_name,RepoTags=[args.target],Layers=['layer.tar'])],
                            sort_keys=True,separators=(',',':')).encode()
        with tarfile.open(folder/'image.tar','w:',format=tarfile.PAX_FORMAT) as archive:
            add_bytes(archive,config_name,config_bytes,args.epoch)
            add_bytes(archive,'manifest.json',manifest,args.epoch)
            info=tarfile.TarInfo('layer.tar');info.mode=0o644;info.size=layer.stat().st_size;info.mtime=args.epoch
            with layer.open('rb') as f:archive.addfile(info,f)
        subprocess.run(['docker','load','--input',str(folder/'image.tar')],check=True)
        expected='sha256:'+config_name.removesuffix('.json')
        actual=run('docker','image','inspect',args.target,'--format','{{.Id}}')
        if actual!=expected:
            raise ValueError('Loaded image config digest differs from the canonical package')
        print('Canonical runtime image:',actual)


if __name__=='__main__':
    main()
