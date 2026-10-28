#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_docker
[[ -f "${PROJECT_ROOT}/certs/ca.crt" ]] || {
  echo "Missing TLS certificates. Run: make certs" >&2
  exit 1
}

docker image inspect "${TRITON_IMAGE}" >/dev/null

docker run --rm --entrypoint /bin/bash "${TRITON_IMAGE}" -Eeuo pipefail -c '
  export LD_LIBRARY_PATH="/opt/tritonserver/lib:${LD_LIBRARY_PATH:-}"
  test "${TRITON_SERVER_GPU_ENABLED}" = "0"
  IFS=, read -r -a backends <<< "${TRITON_BACKENDS:-pytorch,onnxruntime,openvino}"
  for backend in "${backends[@]}"; do
    test -d "/opt/tritonserver/backends/${backend}"
    find "/opt/tritonserver/backends/${backend}" -maxdepth 1 -name "libtriton_${backend}.so" -print -quit | grep -q .
    while IFS= read -r library; do
      if ldd "${library}" | grep "not found" | grep -v "libcuda.so.1 => not found" >/dev/null; then
        ldd "${library}" >&2
        exit 1
      fi
    done < <(find "/opt/tritonserver/backends/${backend}" -maxdepth 1 -name "*.so")
  done
  test ! -d /opt/tritonserver/backends/tensorrt
  if [[ ",${TRITON_BACKENDS:-}," == *,python,* ]]; then
    test -x /opt/tritonserver/backends/python/triton_python_backend_stub
    python3 -c "import numpy; import ssl; assert numpy.ones(4).sum() == 4"
  fi
  test ! -e /opt/tritonserver/backends/openvino/libopenvino_intel_gpu_plugin.so
  test ! -e /opt/tritonserver/backends/openvino/libopenvino_intel_npu_plugin.so
  ! command -v clang
  ! command -v gcc
  ! command -v cmake
'

docker compose --project-directory "${PROJECT_ROOT}" up --detach --build

for _ in $(seq 1 60); do
  if docker run --rm --network triton-cpu \
    --volume "${PROJECT_ROOT}/certs:/certs:ro" \
    "$(locked_image curl)" --fail --silent --show-error \
    --cacert /certs/ca.crt https://gateway:8443/v2/health/ready >/dev/null; then
    break
  fi
  sleep 2
done

curl_container=(
  docker run --rm --network triton-cpu
  --volume "${PROJECT_ROOT}/certs:/certs:ro"
  "$(locked_image curl)" --fail --silent --show-error
  --cacert /certs/ca.crt
)
"${curl_container[@]}" https://gateway:8443/v2/health/live >/dev/null
"${curl_container[@]}" https://gateway:8443/v2/systemsharedmemory/status | grep -q '^\['
"${curl_container[@]}" https://gateway:8443/metrics | grep -q '^nv_'

docker run --rm \
  --network triton-cpu \
  --volume "${PROJECT_ROOT}/certs:/certs:ro" \
  --volume "${PROJECT_ROOT}/tests:/tests:ro" \
  "$(locked_image grpcurl)" \
  -cacert /certs/ca.crt \
  -authority gateway \
  -import-path /tests \
  -proto triton-health.proto \
  gateway:8444 inference.GRPCInferenceService/ServerLive | grep -q '"live": true'

echo "Verified CPU-only backends, HTTPS, gRPC TLS, system shared memory, health, and metrics."
