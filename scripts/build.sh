#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

reuse=0
for option in "$@"; do
  case "${option}" in
    --clean) export CLEAN_BUILD=1 ;;
    --reuse-artifacts) reuse=1 ;;
    *) echo 'Usage: scripts/build.sh [--clean|--reuse-artifacts]' >&2; exit 2 ;;
  esac
done
[[ "${CLEAN_BUILD:-0}" != 1 || "${reuse}" == 0 ]] || { echo '--clean and --reuse-artifacts conflict.' >&2; exit 2; }
require_docker
"${PROJECT_ROOT}/scripts/bootstrap.sh"

echo "Building ${TRITON_IMAGE} from ${TRITON_SOURCE_COMMIT} with ${BUILD_JOBS} jobs"
"${PROJECT_ROOT}/scripts/generate.sh"
if [[ "${reuse}" == 1 ]]; then
  python3 "${PROJECT_ROOT}/scripts/build-receipt.py" verify
  docker image inspect tritonserver:latest tritonserver_buildbase:latest >/dev/null
  echo 'Reusing existing core/framework artifacts; compiling Python from its pinned source.'
else
  rm -rf "${GENERATED_DIR}/install" "${GENERATED_DIR}/ci"
  tooling_run bash "${GENERATED_DIR}/docker_build"
  python3 "${PROJECT_ROOT}/scripts/build-receipt.py" write
fi
"${PROJECT_ROOT}/scripts/build-python.sh"

"${PROJECT_ROOT}/scripts/assemble.sh" --tag "${TRITON_IMAGE}"
tooling_run docker image inspect "${TRITON_IMAGE}" \
  --format 'built {{.Id}} ({{.Size}} bytes)'
echo "Built ${TRITON_IMAGE}"
