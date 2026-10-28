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

locked_image() {
  python3 "${PROJECT_ROOT}/scripts/dependencies.py" image "$1"
}

dependency_image() {
  python3 "${PROJECT_ROOT}/scripts/dependencies.py" tag "$1"
}

build_tooling_image() {
  if ! docker image inspect "$(dependency_image core)" >/dev/null 2>&1; then
    "${PROJECT_ROOT}/scripts/prepare-dependencies.sh"
  fi
  docker tag "$(dependency_image core)" "${TOOLING_IMAGE}"
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

  args+=("$(dependency_image core)" "$@")
  "${args[@]}"
}

assert_source_lock() {
  python3 "${PROJECT_ROOT}/scripts/sources.py" --verify
  python3 - "${PROJECT_ROOT}/config/sources.lock.json" "${TRITON_SOURCE_COMMIT}" "${PYTHON_BACKEND_COMMIT}" <<'PYLOCK'
import json,sys
rows={r['id']:r['commit'] for r in json.load(open(sys.argv[1]))['repositories']}
if rows['server']!=sys.argv[2] or rows['python_backend']!=sys.argv[3]:
    sys.exit('build.env source commits do not match sources.lock.json')
PYLOCK
  [[ "${TRITON_GPU_BASE_IMAGE}" == "$(locked_image nvidia-min)" ]] || {
    echo 'GPU base image does not match images.lock.json.' >&2; exit 1;
  }
  local actual
  actual=$(git -C "${SOURCE_DIR}" rev-parse HEAD)
  [[ "${actual}" == "${TRITON_SOURCE_COMMIT}" ]] || {
    echo "Generator source mismatch: ${actual}" >&2; exit 1;
  }
  [[ -z $(git -C "${SOURCE_DIR}" status --porcelain --untracked-files=no) ]] || {
    echo 'Generator source has tracked modifications.' >&2; exit 1;
  }
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
    "--override-backend-cmake-arg=pytorch:TRITON_PYTORCH_DOCKER_IMAGE=$(locked_image pytorch)"
    "--backend=onnxruntime:${TRITON_GIT_REF}"
    "--backend=openvino:${TRITON_GIT_REF}"
    --override-backend-cmake-arg=onnxruntime:TRITON_ENABLE_ONNXRUNTIME_OPENVINO=OFF
    --no-container-source
  )
}
