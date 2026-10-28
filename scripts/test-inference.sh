#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
export TRITON_IMAGE
backends=$(docker image inspect "${TRITON_IMAGE}" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^TRITON_BACKENDS=//p')
backends=${backends:-pytorch,onnxruntime,openvino}
models=
load_args=
IFS=, read -r -a selected <<< "${backends}"
for backend in "${selected[@]}"; do
  case "${backend}" in
    pytorch) model=smoke_pytorch ;;
    onnxruntime) model=smoke_onnx ;;
    openvino) model=smoke_openvino ;;
    python) model=smoke_bls; load_args+=' --load-model=smoke_python_child' ;;
    *) echo "Unknown backend in image: ${backend}" >&2; exit 1 ;;
  esac
  models+="${model},"
  load_args+=" --load-model=${model}"
done
export TEST_LOAD_ARGS="${load_args}"
test_image=local/triton-cpu-tests:26.09
mkdir -p "${PROJECT_ROOT}/.work/test-models"
docker build --network=none --build-arg "TEST_IMAGE=$(dependency_image tests)" -f "${PROJECT_ROOT}/Dockerfile.tests" -t "${test_image}" "${PROJECT_ROOT}"
docker run --rm --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  -v "${PROJECT_ROOT}/.work/test-models:/models" "${test_image}" /tests/generate_models.py
compose=(docker compose --project-directory "${PROJECT_ROOT}" -f "${PROJECT_ROOT}/compose.yaml" -f "${PROJECT_ROOT}/tests/compose.yaml")
"${compose[@]}" up --detach --build --wait --force-recreate
triton_id=$("${compose[@]}" ps -q triton)
report_dir="${PROJECT_ROOT}/artifacts/assemblies/${TRITON_IMAGE//[^a-zA-Z0-9._-]/_}"
mkdir -p "${report_dir}"
docker run --rm --user 1000:1000 --network triton-cpu --ipc "container:${triton_id}" \
  --env "SMOKE_MODELS=${models%,}" \
  -v "${PROJECT_ROOT}/certs:/certs:ro" "${test_image}" /tests/inference.py \
  | tee "${report_dir}/inference-verification.txt"
echo 'Inference acceptance tests passed. Test stack remains running; use ./triton stop to stop it.'
