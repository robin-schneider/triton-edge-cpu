#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_docker
# NVIDIA's generator clones release branches. Fail before compilation when a
# branch moves, rather than silently building a different source revision.
# shellcheck disable=SC2016
tooling_run bash -Eeuo pipefail -c '
  while read -r repository branch expected; do
    [[ -z "${repository}" || "${repository}" == \#* ]] && continue
    actual=$(git ls-remote "https://github.com/triton-inference-server/${repository}.git" "refs/heads/${branch}")
    actual=${actual%%[[:space:]]*}
    if [[ "${actual}" != "${expected}" ]]; then
      echo "Source drift: ${repository}/${branch}: expected ${expected}, got ${actual}. Review config/source-lock.tsv before rebuilding." >&2
      exit 1
    fi
  done < "$1"
' check-source-lock "${PROJECT_ROOT}/config/source-lock.tsv"
echo 'Release source branches match the recorded component commits.'
