# Build design

## Sources and build stages

`config/build.env` selects Triton 2.73.0 / release 26.09 and pins the server and
Python backend commits. `config/source-lock.tsv` records the other component
commits. Before compilation, generation checks NVIDIA's release branch heads
against that lock and fails on drift. Update the release inputs and lock
together when upgrading.

The build has three boundaries:

1. A Docker tooling image fetches sources and runs NVIDIA's `build.py` to
   generate and execute the core and framework build stages.
2. `Dockerfile.python` compiles the Python backend and combines it with those
   artifacts, Python 3.12 and NumPy.
3. `Dockerfile.runtime` resolves runtime dependencies from the artifact image
   and copies them into a clean Ubuntu 24.04 image. It excludes compilers,
   SDK headers, build trees and test dependencies.

The project is mounted at the same absolute path inside the tooling container
so the host Docker daemon can resolve nested bind mounts. Dependency resolution
uses the artifact image's libraries, never the host's libraries. Ubuntu matches
the generated build stages to keep native library ABIs consistent.

Source revisions are checked, but package repositories and container tags can
change; builds are not guaranteed to be bit-for-bit identical. Artifact
collection records build settings, generated recipes, source commits, image
metadata, an SPDX SBOM and checksums.

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
