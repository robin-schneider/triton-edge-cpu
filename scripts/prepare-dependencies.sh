#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
python3 "${PROJECT_ROOT}/scripts/inputs.py"
python3 "${PROJECT_ROOT}/scripts/dependency-context.py"
args=(--network=none --platform=linux/amd64 --progress=plain)
[[ "${CLEAN_BUILD:-0}" == 1 ]] && args+=(--no-cache)
for pair in UBUNTU_IMAGE:ubuntu NVIDIA_IMAGE:nvidia-min PYTHON_IMAGE:python SHELLCHECK_IMAGE:shellcheck; do
  args+=(--build-arg "${pair%%:*}=$(locked_image "${pair#*:}")")
done
for target in core onnxruntime openvino python runtime tests; do
  image=$(dependency_image "${target}")
  if [[ "${CLEAN_BUILD:-0}" != 1 ]] && python3 "${PROJECT_ROOT}/scripts/dependencies.py" cached "${target}"; then
    continue
  fi
  docker build "${args[@]}" --target "${target}" --tag "${image}" \
    "${PROJECT_ROOT}/.work/dependency-context"
  python3 "${PROJECT_ROOT}/scripts/dependencies.py" record "${target}"
done
docker tag "$(dependency_image core)" "${TOOLING_IMAGE}"
echo 'All dependency images were built offline from locked public inputs.'
