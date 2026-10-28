#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
command -v git >/dev/null
command -v python3 >/dev/null
# Stage one: fetch exact commits only. All recursive modules resolve locally.
python3 "${PROJECT_ROOT}/scripts/sources.py"
if [[ ! -d "${SOURCE_DIR}/.git" ]]; then
  git clone --no-hardlinks "${PROJECT_ROOT}/.work/sources/checkouts/server" "${SOURCE_DIR}"
  git -C "${SOURCE_DIR}" checkout --detach "${TRITON_SOURCE_COMMIT}"
fi
assert_source_lock
"${PROJECT_ROOT}/scripts/prepare-dependencies.sh"
echo 'Locked sources and dependency artifacts are ready.'
