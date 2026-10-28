#!/usr/bin/env bash
# Install a complete, previously hash-verified closure using a file-only repo.
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
cd /tmp/debs
packages=()
: > Packages
for archive in ./*.deb; do
  dpkg-deb --field "${archive}" >> Packages
  printf 'Filename: %s\nSize: %s\nSHA256: %s\n\n' \
    "${archive}" "$(stat -c %s "${archive}")" "$(sha256sum "${archive}" | cut -d ' ' -f 1)" >> Packages
  packages+=("$(dpkg-deb --field "${archive}" Package)=$(dpkg-deb --field "${archive}" Version)")
done
rm -f /etc/apt/sources.list.d/*
printf 'deb [trusted=yes] file:/tmp/debs ./\n' > /etc/apt/sources.list
rm -rf /var/lib/apt/lists/*
apt-get update
apt-get install -y --no-install-recommends --allow-downgrades "${packages[@]}"
rm -rf /tmp/debs /var/lib/apt/lists/*
rm -f /etc/apt/sources.list
