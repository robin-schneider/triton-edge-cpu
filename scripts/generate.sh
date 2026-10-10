#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_docker
assert_source_lock
"${PROJECT_ROOT}/scripts/check-source-lock.sh"
set_build_args

# Variables in this program are intentionally expanded by the inner shell.
# shellcheck disable=SC2016
tooling_run bash -Eeuo pipefail -c '
  cd "$1"
  shift
  python3 ./build.py --dryrun "$@"
' generate "${SOURCE_DIR}" "${TRITON_BUILD_ARGS[@]}"

# NVIDIA's OpenVINO backend generator enables Intel GPU and NPU plugins by
# default on x86-64 and exposes no forwarding option for their CMake flags.
# Put the reviewed downstream patch in the build context and make the generated
# backend clone apply it before its own nested Docker build.
mkdir -p "${SOURCE_DIR}/.cpu-build"
cp "${PROJECT_ROOT}/patches/openvino-cpu-only.patch" \
  "${SOURCE_DIR}/.cpu-build/openvino-cpu-only.patch"
sed -i \
  's#; git --git-dir openvino/.git log#; git -C openvino apply /workspace/.cpu-build/openvino-cpu-only.patch; git --git-dir openvino/.git log#' \
  "${GENERATED_DIR}/cmake_build"
grep -q -- 'git -C openvino apply /workspace/.cpu-build/openvino-cpu-only.patch' \
  "${GENERATED_DIR}/cmake_build"

echo "Generated NVIDIA build stages in ${GENERATED_DIR}"
