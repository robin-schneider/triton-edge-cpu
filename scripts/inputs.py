#!/usr/bin/env python3
"""Acquire checksum-locked build artifacts; never resolve package versions."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import email
import re
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def verify_wheel(row, path):
    if 'wheel_tags' not in row:
        return
    with zipfile.ZipFile(path) as wheel:
        names=wheel.namelist()
        metadata=email.message_from_bytes(wheel.read(next(n for n in names if n.endswith('.dist-info/METADATA'))))
        header=email.message_from_bytes(wheel.read(next(n for n in names if n.endswith('.dist-info/WHEEL'))))
    normalize=lambda name: re.sub(r'[-_.]+','-',name.lower())
    if (normalize(metadata['Name'])!=normalize(row['name']) or
        metadata['Version']!=row['version'] or
        set(header.get_all('Tag',[]))!=set(row['wheel_tags'])):
        raise ValueError(f'Wheel identity/platform differs from the original installed artifact: {path}')


def fetch(row, destination, verify=False):
    if destination.exists() and sha256(destination) == row['sha256']:
        verify_wheel(row, destination)
        return
    if verify:
        raise ValueError(f'Missing or modified locked input: {destination}')
    url = urllib.parse.urlparse(row['url'])
    if url.scheme != 'https' or url.hostname not in {
        'github.com', 'codeload.github.com', 'archives.boost.io',
        'storage.openvinotoolkit.org', 'snapshot.ubuntu.com',
        'archive.ubuntu.com', 'security.ubuntu.com', 'download.docker.com',
        'files.pythonhosted.org', 'download.pytorch.org', 'download-r2.pytorch.org',
    }:
        raise ValueError(f'Unapproved artifact origin: {row["url"]}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix+'.partial')
    try:
        with urllib.request.urlopen(row['url'], timeout=120) as response, tmp.open('wb') as f:
            shutil.copyfileobj(response, f)
        if sha256(tmp) != row['sha256']:
            raise ValueError(f'Checksum mismatch: {row["url"]}')
        verify_wheel(row, tmp)
        os.replace(tmp, destination)
    finally:
        tmp.unlink(missing_ok=True)


def unpack(archive, destination):
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for n in z.namelist():
                if not (destination/n).resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Unsafe archive member: '+n)
            z.extractall(destination)
    else:
        with tarfile.open(archive) as t:
            t.extractall(destination, filter='data')
    entries = list(destination.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        temporary = destination.with_name(destination.name+'.unpack')
        entries[0].rename(temporary)
        destination.rmdir()
        temporary.rename(destination)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--verify', action='store_true')
    p.add_argument('--directory', type=Path, default=ROOT/'.work/inputs')
    args = p.parse_args()
    jobs = []
    root = args.directory
    archives = json.loads((ROOT/'config/archives.lock.json').read_text())['archives']
    for row in archives:
        jobs.append((row, root/'archives'/row['sha256']/row['filename']))
    for name in ['core', 'onnxruntime', 'openvino', 'python', 'runtime']:
        for row in json.loads((ROOT/f'config/locks/{name}.apt.json').read_text()):
            jobs.append((row, root/'apt'/name/row['filename']))
    for name in ['core', 'onnxruntime', 'openvino', 'python', 'tests']:
        for row in json.loads((ROOT/f'config/locks/{name}.wheels.json').read_text()):
            jobs.append((row, root/'wheels'/name/row['filename']))
    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(lambda pair: fetch(*pair, verify=args.verify), jobs))
    if not args.verify:
        for row in archives:
            destination = root/'unpacked'/row['id']
            unpack(root/'archives'/row['sha256']/row['filename'], destination)
    print(f'Verified {len(jobs)} locked package/archive artifacts.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as e:
        sys.exit(str(e))
