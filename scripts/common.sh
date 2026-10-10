#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_CONFIG="${BUILD_CONFIG:-${PROJECT_ROOT}/config/build.env}"

if [[ ! -f "${BUILD_CONFIG}" ]]; then
  echo "Missing build config: ${BUILD_CONFIG}" >&2
  exit 1
fi

# Keep explicit command-line environment overrides after loading defaults/.env.
declare -A process_overrides=()
for override_name in TRITON_IMAGE TOOLING_IMAGE GATEWAY_IMAGE BUILD_JOBS EXPORT_IMAGE; do
  [[ -v "${override_name}" ]] && process_overrides["${override_name}"]=${!override_name}
done
# shellcheck disable=SC1090
source "${BUILD_CONFIG}"
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${PROJECT_ROOT}/.env"
fi
for override_name in "${!process_overrides[@]}"; do
  printf -v "${override_name}" '%s' "${process_overrides[${override_name}]}"
done

SOURCE_DIR="${PROJECT_ROOT}/.work/server"
# Referenced by scripts that source this library.
# shellcheck disable=SC2034
GENERATED_DIR="${SOURCE_DIR}/build"

require_docker() {
  command -v docker >/dev/null 2>&1 || {
    echo "Docker CLI is required." >&2
    exit 1
  }
  docker info >/dev/null 2>&1 || {
    echo 'Docker is unavailable. Start Docker and ensure your user can run docker info.' >&2
    exit 1
  }
}

build_tooling_image() {
  docker build \
    --file "${PROJECT_ROOT}/Dockerfile.tooling" \
    --tag "${TOOLING_IMAGE}" \
    "${PROJECT_ROOT}"
}

tooling_run() {
  local -a args=(
    docker run --rm
    --user "$(id -u):$(id -g)"
    --env HOME=/tmp/tooling-home
    --volume "${PROJECT_ROOT}:${PROJECT_ROOT}"
    --workdir "${PROJECT_ROOT}"
  )

  if [[ -S /var/run/docker.sock ]]; then
    args+=(
      --group-add "$(stat -c '%g' /var/run/docker.sock)"
      --volume /var/run/docker.sock:/var/run/docker.sock
    )
  fi

  args+=("${TOOLING_IMAGE}" "$@")
  "${args[@]}"
}

assert_source_lock() {
  [[ -d "${SOURCE_DIR}/.git" ]] || {
    echo "Triton source is absent. Run: make bootstrap" >&2
    exit 1
  }
  local actual
  actual="$(tooling_run git -C "${SOURCE_DIR}" rev-parse HEAD)"
  if [[ "${actual}" != "${TRITON_SOURCE_COMMIT}" ]]; then
    echo "Source lock mismatch: expected ${TRITON_SOURCE_COMMIT}, got ${actual}" >&2
    exit 1
  fi
}

set_build_args() {
  # Referenced by scripts that call this library function.
  # shellcheck disable=SC2034
  TRITON_BUILD_ARGS=(
    --verbose
    --no-container-interactive
    --target-platform=linux
    --target-machine=x86_64
    "--build-parallel=${BUILD_JOBS}"
    "--version=${TRITON_VERSION}"
    "--container-version=${TRITON_CONTAINER_VERSION}"
    "--triton-container-version=${TRITON_CONTAINER_VERSION}"
    "--upstream-container-version=${TRITON_UPSTREAM_CONTAINER_VERSION}"
    "--image=gpu-base,${TRITON_GPU_BASE_IMAGE}"
    --enable-logging
    --enable-stats
    --enable-metrics
    --enable-cpu-metrics
    --enable-tracing
    --endpoint=http
    --endpoint=grpc
    "--repo-tag=common:${TRITON_GIT_REF}"
    "--repo-tag=core:${TRITON_GIT_REF}"
    "--repo-tag=backend:${TRITON_GIT_REF}"
    "--repo-tag=thirdparty:${TRITON_GIT_REF}"
    "--backend=pytorch:${TRITON_GIT_REF}"
    "--backend=onnxruntime:${TRITON_GIT_REF}"
    "--backend=openvino:${TRITON_GIT_REF}"
    --override-backend-cmake-arg=onnxruntime:TRITON_ENABLE_ONNXRUNTIME_OPENVINO=OFF
    --no-container-source
  )
}
