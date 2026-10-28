#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_docker
mkdir -p "${PROJECT_ROOT}/certs"

docker build --network=none \
  --build-arg "CERT_IMAGE=$(dependency_image runtime)" \
  --file "${PROJECT_ROOT}/Dockerfile.gateway" \
  --target cert-tools \
  --tag "${GATEWAY_IMAGE}-cert-tools" \
  "${PROJECT_ROOT}"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  --entrypoint /bin/sh \
  --volume "${PROJECT_ROOT}/certs:/out" \
  "${GATEWAY_IMAGE}-cert-tools" -eu -c '
    if [ -e /out/ca.key ] || [ -e /out/server.key ]; then
      echo "Refusing to overwrite existing keys in certs/. Remove them explicitly to rotate." >&2
      exit 1
    fi
    openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 -nodes \
      -keyout /out/ca.key -out /out/ca.crt \
      -subj "/CN=Triton local development CA" \
      -addext "basicConstraints=critical,CA:TRUE" \
      -addext "keyUsage=critical,keyCertSign,cRLSign"
    openssl req -newkey rsa:3072 -sha256 -nodes \
      -keyout /out/server.key -out /out/server.csr \
      -subj "/CN=localhost" \
      -addext "subjectAltName=DNS:localhost,DNS:gateway,DNS:triton.local,IP:127.0.0.1"
    openssl x509 -req -sha256 -days 825 \
      -in /out/server.csr -CA /out/ca.crt -CAkey /out/ca.key \
      -CAcreateserial -copy_extensions copy -out /out/server.crt
    rm /out/server.csr /out/ca.srl
    chmod 600 /out/ca.key /out/server.key
    chmod 644 /out/ca.crt /out/server.crt
  '

echo "Development CA and server certificate created in certs/. Do not use them in production."
