#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=scripts/common.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/assemble.sh [options]
Assemble a clean runtime from already compiled NVIDIA build artifacts.
  --backends LIST            Comma-separated pytorch,onnxruntime,openvino,python
  --source IMAGE             Artifact source image (default: local/triton-cpu-artifacts:26.09)
  --tag IMAGE                Output tag (default: derived from backend selection)
  --openvino-frontends LIST  all (default) or ir,onnx,tensorflow,tensorflow_lite,paddle,pytorch
                            IR is always retained when OpenVINO is selected.
  --keep-onnx-tools          Include upstream test/benchmark executables
  --no-dedup                 Keep repeated OpenVINO library files
  --strip-debug              Strip ELF debug sections; keep dynamic symbols
  --help                    Show usage

Default: all four backends (including Python BLS), remove ONNX tools, deduplicate OpenVINO libraries.
No source compilation is performed. Run make build first on a fresh builder.
EOF
}
backends=pytorch,onnxruntime,openvino,python
source_image=${ARTIFACT_IMAGE}
output_image=
frontends=all
keep_tools=0
dedup=1
strip_debug=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --backends|--source|--tag|--openvino-frontends)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || { echo "Missing value for $1" >&2; exit 2; }
      case "$1" in
        --backends) backends=$2 ;;
        --source) source_image=$2 ;;
        --tag) output_image=$2 ;;
        --openvino-frontends) frontends=$2 ;;
      esac
      shift 2 ;;
    --keep-onnx-tools) keep_tools=1; shift ;;
    --no-dedup) dedup=0; shift ;;
    --strip-debug) strip_debug=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
[[ "${backends}" =~ ^(pytorch|onnxruntime|openvino|python)(,(pytorch|onnxruntime|openvino|python))*$ ]] \
  || { echo "Invalid backend list: ${backends}" >&2; exit 2; }
[[ "${frontends}" == all || "${frontends}" =~ ^(ir|onnx|tensorflow|tensorflow_lite|paddle|pytorch)(,(ir|onnx|tensorflow|tensorflow_lite|paddle|pytorch))*$ ]] \
  || { echo "Invalid frontend list: ${frontends}" >&2; exit 2; }
# Canonical ordering and de-duplication give stable tags and COPY inputs.
selection=,
for backend in pytorch onnxruntime openvino python; do
  [[ ",${backends}," == *",${backend},"* ]] && selection+="${backend},"
done
backends=${selection#,}
backends=${backends%,}
if [[ -z "${output_image}" ]]; then
  if [[ "${backends}" == pytorch,onnxruntime,openvino,python ]]; then
    output_image=${TRITON_IMAGE}
  else
    output_image="local/tritonserver-cpu-${backends//,/-}:${TRITON_CONTAINER_VERSION}"
  fi
fi
[[ "${source_image}" != "${output_image}" ]] || { echo 'Source and output tags must differ.' >&2; exit 2; }
require_docker
source_id=$(docker image inspect "${source_image}" --format '{{.Id}}') || {
  echo "Source image is absent. Run make build or load the compiled source image first." >&2; exit 1;
}
source_env=$(docker image inspect "${source_image}" --format '{{range .Config.Env}}{{println .}}{{end}}')
if ! grep -qx 'TRITON_SERVER_GPU_ENABLED=0' <<< "${source_env}" \
  || ! grep -qx "TRITON_SERVER_VERSION=${TRITON_VERSION}" <<< "${source_env}"; then
  echo "Source must be a CPU-only Triton ${TRITON_VERSION} artifact image." >&2
  exit 2
fi
[[ $(docker image inspect "${source_image}" --format '{{.Os}}/{{.Architecture}}') == linux/amd64 ]] \
  || { echo 'This recipe requires a Linux x86-64 source image.' >&2; exit 2; }
docker build -f "${PROJECT_ROOT}/Dockerfile.runtime" -t "${output_image}" \
  --build-arg "UPSTREAM_IMAGE=${source_image}" --build-arg "BACKENDS=${backends}" \
  --build-arg "OPENVINO_FRONTENDS=${frontends}" --build-arg "KEEP_ONNX_TOOLS=${keep_tools}" \
  --build-arg "DEDUP_OPENVINO=${dedup}" --build-arg "STRIP_DEBUG=${strip_debug}" "${PROJECT_ROOT}"
report_dir="${PROJECT_ROOT}/artifacts/assemblies/${output_image//[^a-zA-Z0-9._-]/_}"
mkdir -p "${report_dir}"
printf 'source_image=%s\nsource_id=%s\nbackends=%s\nopenvino_frontends=%s\nkeep_onnx_tools=%s\ndedup_openvino=%s\nstrip_debug=%s\n' \
  "${source_image}" "${source_id}" "${backends}" "${frontends}" "${keep_tools}" "${dedup}" "${strip_debug}" > "${report_dir}/assembly.env"
docker image inspect "${output_image}" > "${report_dir}/image-inspect.json"
docker image inspect "${output_image}" --format 'Assembled {{.RepoTags}}: {{.Size}} bytes ({{.Id}})'
echo "Validate before deployment: TRITON_IMAGE=${output_image} make test"
