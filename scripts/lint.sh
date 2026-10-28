#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_docker
build_tooling_image
tooling_run shellcheck triton scripts/*.sh
python3 -m unittest discover -s tests -p 'test_build_locks.py'
docker compose --project-directory "${PROJECT_ROOT}" config --quiet
docker compose --project-directory "${PROJECT_ROOT}" -f compose.yaml -f tests/compose.yaml config --quiet
./scripts/assemble.sh --help >/dev/null
./triton --help >/dev/null
for invalid in '' cuda 'onnxruntime,'; do
  if ./scripts/assemble.sh --backends "${invalid}" >/dev/null 2>&1; then
    echo "Assembly accepted invalid backend list: ${invalid}" >&2
    exit 1
  fi
done

grep -q -- '--backend=pytorch' scripts/common.sh
grep -q -- '--backend=onnxruntime' scripts/common.sh
grep -q -- '--backend=openvino' scripts/common.sh
grep -q -- 'ENABLE_INTEL_GPU=OFF' patches/openvino-cpu-only.patch
grep -q -- 'ENABLE_INTEL_NPU=OFF' patches/openvino-cpu-only.patch
grep -q -- '--endpoint=http' scripts/common.sh
grep -q -- '--endpoint=grpc' scripts/common.sh
grep -q -- '--enable-cpu-metrics' scripts/common.sh
if grep -q -- '--enable-gpu\|--enable-gpu-metrics' scripts/common.sh; then
  echo "CPU-only build accidentally enables a GPU feature." >&2
  exit 1
fi

echo "Static validation passed."
