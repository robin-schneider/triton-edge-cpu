# Build design

## Sources and build stages

`config/build.env` selects Triton 2.73.0 / release 26.09. The complete Git
closure is in `config/sources.lock.json`; every checkout uses a full commit
hash, a depth-one fetch, and no tags. Upstream release branches may move without
changing this build. Nested submodules resolve through local locked mirrors.

`config/images.lock.json` pins public OCI inputs by digest and restricts them
to Docker Hub and NVIDIA NGC. `config/locks/` pins the apt closure and exact
Python wheels, including test packages and isolated wheel-build dependencies.
`config/archives.lock.json` records SHA-256 hashes for source and binary archives
already used by the previous build. No custom registry or image publishing is
required. See [reproducibility](reproducibility.md) for the acquisition boundary
and validation commands.

The build has three boundaries:

1. Bootstrap checks out Git sources and stages all checksum-verified artifact
   inputs. `Dockerfile.dependencies` reconstructs compiler, framework, runtime
   and test environments from those inputs with network disabled.
2. NVIDIA's pinned generator produces core/framework recipes. Reviewed
   transformations substitute local source checkouts and archive inputs, remove
   live package resolution, and disable networking for every compiler container and
   nested Docker build. `Dockerfile.python` adds the Python backend.
3. `Dockerfile.runtime` copies the selected backend artifacts and their ELF
   dependencies into a locked Ubuntu runtime environment.

The project is mounted at the same absolute path inside the tooling container
so the host Docker daemon can resolve nested bind mounts. Dependency resolution
uses the artifact image's libraries, never the host's libraries. All compiler
inputs are fixed; `SOURCE_DATE_EPOCH`, locale and Python hashing are controlled.
The final runtime is repackaged with deterministic filesystem and image
metadata. Comparing independent clean build IDs verifies output identity;
package and source checks verify the availability and completeness of inputs.

## CPU runtime

The build enables PyTorch, ONNX Runtime, standalone OpenVINO and Python/BLS;
HTTP and gRPC; logging, statistics, metrics, CPU metrics and tracing.
GPU support, GPU metrics and TensorRT are disabled. The OpenVINO patch disables
Intel GPU and NPU plugins, and ONNX Runtime's OpenVINO execution provider is
excluded because the standalone backend supplies that functionality.

Cloud filesystems, caches, repository agents, SDK tools and upstream QA images
are excluded from deployment. Packaging removes ONNX test executables and
replaces identical OpenVINO library copies with symlinks. Assemblies can select
backend subsets, retain fewer OpenVINO frontends or strip ELF debug sections.

NVIDIA's PyTorch dependencies still include CUDA-linked libraries even with
`TRITON_SERVER_GPU_ENABLED=0`. These dominate the default image's size but do
not require GPU devices to serve CPU models.

## Serving boundary

The runtime runs as UID/GID 1000. NGINX terminates TLS for HTTPS (`8443`) and
gRPCS (`8444`); Triton's ports `8000`, `8001` and `8002` remain on the private
Compose network. Generated certificates are for development.

Compose allocates configurable shared memory, uses shareable IPC and enables
`--allow-client-shm=true`. System shared memory is supported over both inference
protocols; CUDA shared memory is unavailable.

The gateway exposes health and metadata APIs, `/metrics` (including Python
custom metrics), model statistics, trace settings and logging settings.
Process logs go to container stdout/stderr. Tracing is compiled in; deployments
must configure collection and sampling at runtime.
