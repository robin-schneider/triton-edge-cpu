#!/usr/bin/env bash
# Executed only inside the packaging stage. Resolve ELF dependencies from the
# matching upstream image, preserving paths and symlinks, without its toolchain.
set -Eeuo pipefail
root=/runtime-root
mkdir -p "${root}/opt/tritonserver/backends"
cp -a /opt/tritonserver/{bin,lib,LICENSE,TRITON_VERSION,NVIDIA_Deep_Learning_Container_License.pdf} "${root}/opt/tritonserver/"
cp /tmp/project-license "${root}/opt/tritonserver/PROJECT_LICENSE"
IFS=, read -r -a backends <<< "${BACKENDS:-pytorch,onnxruntime,openvino,python}"
for backend in "${backends[@]}"; do
  case "${backend}" in pytorch|onnxruntime|openvino|python) ;; *) echo "Invalid backend: ${backend}" >&2; exit 1 ;; esac
  cp -a "/opt/tritonserver/backends/${backend}" "${root}/opt/tritonserver/backends/"
done
if [[ ",${BACKENDS}," == *,python,* ]]; then
  # Embedded Python needs its standard library, extension modules and NumPy;
  # ldd alone cannot discover modules imported dynamically by model.py.
  mkdir -p "${root}/usr/lib/python3/dist-packages" "${root}/usr/bin"
  cp -a /usr/lib/python3.12 "${root}/usr/lib/"
  cp -a /usr/lib/python3/dist-packages/numpy* "${root}/usr/lib/python3/dist-packages/"
  cp -a /usr/bin/python3 /usr/bin/python3.12 "${root}/usr/bin/"
  find "${root}/usr/lib/python3.12" "${root}/usr/lib/python3/dist-packages" \
    -type d -name __pycache__ -exec rm -rf {} +
fi
if [[ "${KEEP_ONNX_TOOLS:-0}" == 0 ]]; then
  rm -f "${root}/opt/tritonserver/backends/onnxruntime/onnx_test_runner" \
    "${root}/opt/tritonserver/backends/onnxruntime/onnxruntime_perf_test"
fi
openvino_dir="${root}/opt/tritonserver/backends/openvino"
if [[ -d "${openvino_dir}" ]]; then
  shopt -s nullglob
  if [[ "${OPENVINO_FRONTENDS:-all}" != all ]]; then
    IFS=, read -r -a frontends <<< "${OPENVINO_FRONTENDS}"
    declare -A keep_frontend=([ir]=1)
    for frontend in "${frontends[@]}"; do
      case "${frontend}" in ir|onnx|tensorflow|tensorflow_lite|paddle|pytorch) ;; *) echo "Invalid frontend: ${frontend}" >&2; exit 1 ;; esac
      keep_frontend["${frontend}"]=1
    done
    for library in "${openvino_dir}"/libopenvino_*_frontend.so*; do
      frontend=${library##*/libopenvino_}
      frontend=${frontend%%_frontend.so*}
      [[ -v "keep_frontend[${frontend}]" ]] || rm -f "${library}"
    done
  fi
  if [[ "${DEDUP_OPENVINO:-1}" == 1 ]]; then
    declare -A identical_library=()
    for library in "${openvino_dir}"/*.so*; do
      [[ -f "${library}" && ! -L "${library}" ]] || continue
      digest=$(sha256sum "${library}")
      digest=${digest%% *}
      if [[ -v "identical_library[${digest}]" ]]; then
        ln -sf "${identical_library[${digest}]}" "${library}"
      else
        identical_library["${digest}"]=${library##*/}
      fi
    done
  fi
fi
export LD_LIBRARY_PATH="/opt/tritonserver/lib:${LD_LIBRARY_PATH:-}"
dependencies=$(mktemp)
while IFS= read -r -d '' file; do
  file=${file#"${root}"}
  [[ $(head -c 4 "${file}") == $'\x7fELF' ]] || continue
  # Some installed files are configuration text rather than ELF binaries.
  result=$(ldd "${file}" 2>&1) || {
    if [[ "${result}" == *'not a dynamic executable'* || "${result}" == *'statically linked'* ]]; then
      continue
    fi
    echo "${result}" >&2
    exit 1
  }
  # libtorch_cuda is shipped by NVIDIA even for CPU-only execution. Its
  # optional libcuda driver is supplied only on GPU hosts and is never needed
  # by the CPU backend. Every other unresolved dependency is a packaging error.
  if grep 'not found' <<< "${result}" | grep -v 'libcuda.so.1 => not found' >/dev/null; then
    echo "Unresolved dependency for ${file}: ${result}" >&2
    exit 1
  fi
  awk '/=> \// {print $3} /^[[:space:]]*\// {print $1}' <<< "${result}" >> "${dependencies}"
done < <(find "${root}/opt/tritonserver"/{bin,lib,backends} \
  "${root}/usr/lib/python3.12" "${root}/usr/lib/python3/dist-packages" \
  -type f -print0 2>/dev/null)
sort -u "${dependencies}" | while IFS= read -r library; do
  [[ "${library}" == /opt/tritonserver/* ]] && continue
  # Preserve the entire symlink chain, including Ubuntu alternatives links
  # used by BLAS/LAPACK; copying only the first and final paths breaks NumPy.
  while :; do
    destination="${library}"
    [[ "${destination}" == /lib/* || "${destination}" == /lib64/* ]] && destination="/usr${destination}"
    mkdir -p "${root}$(dirname "${destination}")"
    cp -a "${library}" "${root}${destination}"
    [[ -L "${library}" ]] || break
    target=$(readlink "${library}")
    if [[ "${target}" == /* ]]; then
      library=${target}
    else
      library=$(readlink -m "$(dirname "${library}")/${target}")
    fi
  done
done
if [[ "${STRIP_DEBUG:-0}" == 1 ]]; then
  command -v strip >/dev/null || { echo 'Source image must provide strip.' >&2; exit 1; }
  while IFS= read -r -d '' file; do
    # Only ELF files: preserve configuration, licenses and dynamic symbols.
    if [[ $(head -c 4 "${file}") == $'\x7fELF' ]]; then
      strip --strip-debug "${file}"
    fi
  done < <(find "${root}/opt/tritonserver"/{bin,lib,backends} -type f -print0)
fi
# Retain upstream redistribution notices for copied system libraries.
mkdir -p "${root}/usr/share"
cp -a /usr/share/doc "${root}/usr/share/"
