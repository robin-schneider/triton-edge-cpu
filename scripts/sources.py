#!/usr/bin/env python3
"""Fetch only locked commits, then prepare offline Git mirrors and checkouts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def git(*args, env=None, capture=False):
    return subprocess.run(['git', '-c', 'safe.directory=*', *map(str, args)],
                          env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def key(url):
    return hashlib.sha256(url.lower().removesuffix('.git').encode()).hexdigest()[:20]


def manifest(path):
    data = json.loads(path.read_text())
    ids, refs = set(), {}
    for row in data['repositories']:
        if row['id'] in ids or not re.fullmatch(r'[0-9a-f]{40}', row['commit']):
            raise ValueError(f'Invalid/duplicate source lock: {row}')
        ids.add(row['id'])
        if not re.fullmatch(r'https://github.com/[\w.-]+/[\w.-]+(?:\.git)?', row['url']):
            raise ValueError(f'Unsupported source URL: {row["url"]}')
        for ref in row.get('refs', []):
            if not re.fullmatch(r'refs/(heads|tags)/[\w./+-]+', ref):
                raise ValueError(f'Invalid reference: {ref}')
            alias = (key(row['url']), ref)
            if alias in refs and refs[alias] != row['commit']:
                raise ValueError(f'Ambiguous locked reference: {alias}')
            refs[alias] = row['commit']
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=ROOT/'config/sources.lock.json')
    parser.add_argument('--directory', type=Path, default=ROOT/'.work/sources')
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--jobs', type=int, default=6)
    args = parser.parse_args()
    data = manifest(args.lock)
    directory = args.directory.resolve()
    mirrors = directory/'git'
    checkouts = directory/'checkouts'
    mirrors.mkdir(parents=True, exist_ok=True)
    checkouts.mkdir(exist_ok=True)
    # Never use personal URL rewrites, alternates or credentials in the lock.
    fetch_env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null',
                     GIT_CONFIG_SYSTEM='/dev/null', GIT_TERMINAL_PROMPT='0',
                     GIT_ALLOW_PROTOCOL='https:file')
    by_url = {}
    for row in data['repositories']:
        by_url.setdefault(key(row['url']), []).append(row)

    def fetch(rows):
        mirror = mirrors/key(rows[0]['url'])
        if not mirror.exists():
            git('init', '--bare', mirror, env=fetch_env)
        for row in rows:
            if not args.verify:
                present = subprocess.run(['git', '-C', str(mirror), 'cat-file', '-e',
                                          row['commit']+'^{commit}'],
                                         stderr=subprocess.DEVNULL).returncode == 0
                if not present:
                    git('-C', mirror, 'fetch', '--no-tags', '--depth=1',
                        row['url'], row['commit'], env=fetch_env)
                git('-C', mirror, 'update-ref', 'refs/locks/'+row['commit'], row['commit'])
                for ref in row.get('refs', []):
                    git('-C', mirror, 'update-ref', ref, row['commit'])
            for ref in row.get('refs', []):
                locked = git('-C', mirror, 'rev-parse', ref+'^{commit}', capture=True).strip()
                if locked != row['commit']:
                    raise ValueError('Modified local source alias: '+ref)
            actual = git('-C', mirror, 'rev-parse', row['commit']+'^{commit}', capture=True).strip()
            if actual != row['commit']:
                raise ValueError('Commit mismatch: '+row['id'])

        allowed={ref for row in rows for ref in row.get('refs', [])}
        allowed |= {'refs/locks/'+row['commit'] for row in rows}
        allowed |= {'refs/heads/lock-'+row['commit'] for row in rows}
        refs=set(git('-C',mirror,'for-each-ref','--format=%(refname)',capture=True).splitlines())
        commits=set(git('-C',mirror,'rev-list','--all',capture=True).splitlines())
        if refs-allowed or commits!={row['commit'] for row in rows}:
            raise ValueError(f'Cached Git mirror contains unlocked refs/history: {mirror}. Remove the source cache before changing locks.')

    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(fetch, by_url.values()))
    config = directory/'gitconfig'
    content = '[protocol]\n\tallow = never\n[protocol "file"]\n\tallow = always\n'
    for rows in by_url.values():
        # Include every observed spelling (GitHub repository paths ignore case).
        variants = {r['url'] for r in rows}
        variants |= {u.removesuffix('.git') for u in variants}
        variants |= {u+'.git' for u in list(variants) if not u.endswith('.git')}
        for url in sorted(variants):
            content += f'[url "file://{mirrors/key(rows[0]["url"])}"]\n\tinsteadOf = {url}\n'
    if not args.verify:
        config.write_text(content)
    elif not config.exists() or config.read_text()!=content:
        raise ValueError('Cached Git transport configuration differs from the source lock')
    offline_env = dict(fetch_env, GIT_CONFIG_GLOBAL=str(config), GIT_ALLOW_PROTOCOL='file')

    def checkout(row):
        destination = checkouts/row['id']
        if not args.verify and not destination.exists():
            git('clone', '--no-checkout', '--no-hardlinks', '--no-local',
                '--no-tags', '--depth=1', '--branch', 'lock-'+row['commit'],
                'file://'+str(mirrors/key(row['url'])), destination, env=offline_env)
        if not args.verify:
            git('-C', destination, 'checkout', '--detach', row['commit'], env=offline_env)
            # Every nested module is fetched locally at its parent's gitlink.
            git('-C', destination, 'submodule', 'update', '--init', '--recursive',
                '--depth=1', env=offline_env)
        actual = git('-C', destination, 'rev-parse', 'HEAD', capture=True).strip()
        dirty = git('-C', destination, 'status', '--porcelain', '--untracked-files=all', capture=True)
        modules = git('-C', destination, 'submodule', 'status', '--recursive', capture=True)
        if actual != row['commit'] or dirty or any(s[:1] != ' ' for s in modules.splitlines()):
            raise ValueError(f'Dirty or mismatched source: {destination}')

    # clone --branch accepts a named ref, never a raw SHA. These refs are
    # created locally and cannot move in response to upstream branch changes.
    if not args.verify:
        for row in data['repositories']:
            git('-C', mirrors/key(row['url']), 'update-ref',
                'refs/heads/lock-'+row['commit'], row['commit'])
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        list(pool.map(checkout, data['repositories']))
    print(f'Verified {len(data["repositories"])} locked source commits and their submodules.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
