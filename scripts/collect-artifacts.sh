#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

require_docker
assert_source_lock
docker image inspect "${TRITON_IMAGE}" >/dev/null

artifact_dir="${PROJECT_ROOT}/artifacts/${TRITON_CONTAINER_VERSION}"
mkdir -p "${artifact_dir}/generated"

for name in Dockerfile Dockerfile.buildbase Dockerfile.cibase cmake_build docker_build; do
  if [[ -f "${GENERATED_DIR}/${name}" ]]; then
    cp "${GENERATED_DIR}/${name}" "${artifact_dir}/generated/${name}"
  fi
done

printf '%s\n' "${TRITON_SOURCE_COMMIT}" > "${artifact_dir}/source.commit"
cp "${BUILD_CONFIG}" "${artifact_dir}/build.env"
cp "${PROJECT_ROOT}/config/source-lock.tsv" "${artifact_dir}/source-lock.tsv"
cp "${PROJECT_ROOT}/Dockerfile.runtime" "${artifact_dir}/generated/"
cp "${PROJECT_ROOT}/Dockerfile.python" "${artifact_dir}/generated/"
cp "${PROJECT_ROOT}/scripts/build-python.sh" "${artifact_dir}/generated/"
cp "${PROJECT_ROOT}/scripts/assemble-runtime.sh" "${artifact_dir}/generated/"
cp "${PROJECT_ROOT}/scripts/assemble.sh" "${artifact_dir}/generated/"
cp "${PROJECT_ROOT}/LICENSE" "${artifact_dir}/PROJECT_LICENSE"
assembly_dir="${PROJECT_ROOT}/artifacts/assemblies/${TRITON_IMAGE//[^a-zA-Z0-9._-]/_}"
for report in assembly.env inference-verification.txt; do
  if [[ -f "${assembly_dir}/${report}" ]]; then
    cp "${assembly_dir}/${report}" "${artifact_dir}/${report}"
  fi
done
cp "${PROJECT_ROOT}/patches/openvino-cpu-only.patch" "${artifact_dir}/generated/"
cp "${PROJECT_ROOT}/docs/validation.md" "${artifact_dir}/validation.md"
"${PROJECT_ROOT}/scripts/image-size.sh" > "${artifact_dir}/image-size.log"
docker image inspect "${GATEWAY_IMAGE}" > "${artifact_dir}/gateway-inspect.json"
docker image inspect "${TRITON_IMAGE}" > "${artifact_dir}/image-inspect.json"
docker history --no-trunc "${TRITON_IMAGE}" > "${artifact_dir}/image-history.txt"

docker run --rm \
  --volume /var/run/docker.sock:/var/run/docker.sock \
  anchore/syft:v1.33.0 "docker:${TRITON_IMAGE}" -o spdx-json \
  > "${artifact_dir}/sbom.spdx.json"

if [[ "${EXPORT_IMAGE}" == "1" ]]; then
  docker save --output "${artifact_dir}/tritonserver-cpu-${TRITON_CONTAINER_VERSION}.tar" "${TRITON_IMAGE}"
fi

(
  cd "${artifact_dir}"
  checksum_tmp="$(mktemp)"
  find . -type f ! -name SHA256SUMS -print0 \
    | sort -z | xargs -0 sha256sum > "${checksum_tmp}"
  mv "${checksum_tmp}" SHA256SUMS
)

echo "Collected build provenance, generated stages, metadata, and SBOM in ${artifact_dir}"
