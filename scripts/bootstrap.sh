#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_docker
build_tooling_image
mkdir -p "${PROJECT_ROOT}/.work"

if [[ ! -d "${SOURCE_DIR}/.git" ]]; then
  # Variables in this program are intentionally expanded by the inner shell.
  # shellcheck disable=SC2016
  tooling_run bash -Eeuo pipefail -c '
    source_dir="$1"
    source_commit="$2"
    source_ref="$3"
    git clone --filter=blob:none --no-checkout https://github.com/triton-inference-server/server.git "${source_dir}"
    git -C "${source_dir}" fetch --depth=1 origin "${source_commit}"
    git -C "${source_dir}" checkout --detach "${source_commit}"
    printf "%s\n" "${source_ref} ${source_commit}" > "${source_dir}/SOURCE_LOCK"
  ' bootstrap "${SOURCE_DIR}" "${TRITON_SOURCE_COMMIT}" "${TRITON_GIT_REF}"
fi

assert_source_lock
echo "Pinned Triton source is ready at ${SOURCE_DIR}"
