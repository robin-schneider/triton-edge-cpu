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

OPENVINO_BUILD_NUMBER="${OPENVINO_BUILD_NUMBER}" \
  ONNXRUNTIME_BUILD_BRANCH="${ONNXRUNTIME_BUILD_BRANCH}" \
  ONNXRUNTIME_BUILD_ABBREV="${ONNXRUNTIME_BUILD_ABBREV}" python3 "${PROJECT_ROOT}/scripts/lock-generated.py"
echo "Generated locked NVIDIA build stages in ${GENERATED_DIR}"
