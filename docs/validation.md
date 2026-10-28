# Validation results

Recorded on 2026-10-10 for Linux x86-64, Triton 2.73.0 / release 26.09.
The default runtime image was
`sha256:9d9b99fdf0d67717d767cc82c3e017920e1b5d3d38696110af8912a357d511a5`.
These are historical measurements, not guarantees for later builds.

## Image sizes

Uncompressed Docker sizes, in decimal MB (1 MB = 1,000,000 bytes):

| Image | MB |
| --- | ---: |
| NVIDIA-generated custom CPU image | 4,785.27 |
| Default runtime: all four backends | 2,648.06 |
| Python/BLS only | 258.85 |
| ONNX Runtime only | 185.95 |
| OpenVINO IR with debug stripping | 245.80 |
| TLS gateway (separate image) | 12.47 |

Clean runtime packaging reduced the custom CPU image by 45%. Most remaining
bytes belong to PyTorch and its CUDA-linked dependencies. These measurements
are not compressed registry download sizes.

`make size` regenerates the breakdown. `artifacts/26.09/image-files.csv`
attributes individual files to components; `package-files.csv` reports files
owned by Ubuntu packages. Copied libraries are measured separately because
package metadata does not account for all runtime files.

## Checks and limits

The default runtime and the three subsets above passed inference over HTTPS
and gRPCS, POSIX shared-memory input, metrics, statistics, trace settings and
logging checks. Python coverage included BLS child calls, error propagation
and custom counter increments; the Python-only image also passed BLS inference
with shared-memory input.

The recorded validation also included:

- `make lint`: shellcheck and Compose rendering.
- `make verify`: CPU flag, backend libraries, dependency resolution, absence
  of OpenVINO GPU/NPU plugins and build tools, TLS health and shared-memory APIs.
- `make artifacts`: build recipes, image metadata, SPDX SBOM and checksums.

The full source build completed; the subsequent Python addition and final
packaging were validated using `./triton --reuse-artifacts`, without repeating
framework compilation. Tests ran without GPU devices or the NVIDIA runtime.
Packaging excludes the optional `libcuda.so.1` driver dependency of CUDA-only
PyTorch libraries from its dependency check; other missing dependencies fail.

The tests cover small deterministic FP32 models on the build host. They do not
establish compatibility or performance for production models or every x86-64
instruction set. Test those models on the target device before deployment.

## Locked clean builds: 2026-10-27

Two consecutive `./triton build --clean` runs completed on the Linux x86-64
build host. Both rebuilt dependency images without cached RUN layers and
compiled Triton, PyTorch backend, ONNX Runtime, OpenVINO and the Python backend
from empty build directories. Compiler and packaging stages had networking
disabled. Downloaded source/package caches were verified against the locks
before each run.

Both canonical runtime images had the identical Docker configuration and
filesystem digest, producing image ID
`sha256:4e3abd3fd94ab609f30f023dbdf4cef82d88272c25aa4ebc17335dc48c2fe3ed`.
The uncompressed size was 2,620,798,990 bytes. The input/recipe lock identifier
was `35dad5b8d0bd92d17ed0`. This is an observed byte-for-byte comparison of two
complete builds on this host, in addition to input pinning.

The input audit verified 96 Git commits in 69 shallow local mirrors, including
recursive submodules, and 693 checksum-locked package/archive records. Mirrors
contained only the declared commits and refs. All nine public OCI inputs were
digest-pinned: seven Docker Hub images and two NVIDIA NGC images. No images
were published.

The reconstructed apt environments matched every original installed package
version: core 363, ONNX Runtime 414, OpenVINO 367, Python 240 and runtime 109.
The five Python dependency environments passed `pip check`; concrete wheel
artifacts and platform tags were locked as well as package versions.

Both clean images passed HTTP and gRPC inference for all four backends, POSIX
shared memory, Python BLS composition, downstream error handling, custom metric
counters, metrics, statistics, tracing and logging checks. `make verify` also
passed the CPU-only library, TLS endpoint, health and shared-memory API checks.
Static validation passed shellcheck, Compose rendering and all four regression
tests for corrupt inputs, wheel variants and invalid source refs.

`artifacts/26.09/reproducibility.json` and the two image inspection reports
record the comparison. Complete compiler logs are under
`artifacts/logs/20261028T033359Z/` and `artifacts/logs/20261028T042820Z/`; those
directory timestamps are UTC. The collected recipes, locks, receipts, SBOM and
checksums accompany the image reports.
