# CPU-only Triton Inference Server

Build and run NVIDIA Triton 2.73.0 (release 26.09) on Linux x86-64 without a
GPU. Compilation, runtime packaging and inference tests run in Docker. The default image
includes PyTorch, ONNX Runtime, OpenVINO and Python with business logic
scripting (BLS), plus system shared memory and Triton's observability APIs.
A separate NGINX gateway exposes HTTPS on `8443` and gRPCS on `8444`.

GPU support is disabled, but NVIDIA's PyTorch libraries retain CUDA-linked
runtime dependencies. The image needs neither GPU devices nor the NVIDIA
container runtime.

## Build and test

Requirements: Linux x86-64, Git, Python 3.12 (standard library only), Docker
Engine with BuildKit and Compose v2. Initial input acquisition needs GitHub,
Ubuntu snapshots, PyPI/PyTorch wheels, Boost/Intel release artifacts, Docker
Hub and NVIDIA NGC. Compilation and packaging run with networking disabled. Allow roughly 32 GiB RAM and 150–200 GiB
free disk for the full build. No host compiler or third-party Python packages are needed.

```bash
./triton
```

This fetches the locked sources, builds `local/tritonserver-cpu:26.09`, generates
development TLS certificates, runs inference acceptance tests and collects
provenance, an SPDX SBOM, size reports and checksums in `artifacts/26.09/`.
The first build takes several hours; subsequent builds use Docker's cache.
Use `./triton build --clean` to rebuild without cached build layers or compiled
artifacts. See [input locks and clean validation](docs/reproducibility.md).
Logs are saved in `artifacts/logs/`. The verified demo remains running.

Tune `BUILD_JOBS` in `config/build.env` for available memory (roughly 2 GiB per
job). Copy `.env.example` to `.env` for local overrides. If NGC requires
credentials in your environment, run `docker login nvcr.io`.

| Command | Purpose |
| --- | --- |
| `./triton build` | Build without acceptance tests. |
| `./triton build --clean` | Reconstruct dependencies and compile without cached layers. |
| `./triton --reuse-artifacts` | Reuse compiled core/framework images; rebuild Python, package, test and collect reports. |
| `./triton test` | Test the selected `TRITON_IMAGE`; leave the demo running. |
| `./triton artifacts` | Regenerate provenance and reports. |
| `./triton --export` | Build, test and also save a portable Docker image archive. |
| `make lint` | Check shell scripts and Compose configuration in Docker. |

`./triton --help` and `make help` list the available commands.

## Serve models

Put models in `models/` using Triton's model-repository layout, then run:

```bash
./triton run
curl --cacert certs/ca.crt https://localhost:8443/v2/health/ready
curl --cacert certs/ca.crt https://localhost:8443/metrics
./triton stop
```

`run` builds a missing image and creates development certificates when absent.
Existing certificates are preserved. Replace them with production certificates
or use your deployment platform's ingress before deployment. Triton's plaintext
ports stay inside the Compose network.

The server runs as UID/GID 1000 with 1 GiB of `/dev/shm` by default; change
`TRITON_SHM_SIZE` in `.env` as needed. System shared-memory clients must join
the server's IPC namespace and use its UID; the acceptance tests demonstrate
this setup. `./triton test` switches the stack to generated test models;
`./triton run` switches it back to `models/`.

Python models have Python 3.12 and NumPy available. Install additional model
packages in a derived Docker image. The [BLS example](tests/bls/model.py)
calls a child model and exposes custom counters through `/metrics`.

## Assemble smaller images

After a build, package a backend subset from the cached
`local/triton-cpu-artifacts:26.09` image without recompiling:

```bash
./triton assemble --backends onnxruntime
./triton assemble --backends onnxruntime,python
./triton assemble --backends openvino --openvino-frontends ir --strip-debug \
  --tag local/tritonserver-cpu-openvino-ir:26.09
TRITON_IMAGE=local/tritonserver-cpu-onnxruntime:26.09 ./triton test
```

Each assembly starts from a clean Ubuntu 24.04 runtime and includes dependencies
for the selected backends. By default, packaging removes ONNX test executables
and deduplicates identical OpenVINO libraries. `./triton assemble --help` lists
source-image, tag, frontend and stripping options. Use distinct tags when
comparing options for the same backend selection.

Assembly settings, image metadata and test results are saved under
`artifacts/assemblies/`. PyTorch retains its CUDA-linked libraries; replacing
LibTorch or reducing ONNX Runtime's operator set requires a separate build.

See [build design](docs/design.md) for source locking, packaging and runtime
boundaries, and [validation results](docs/validation.md) for recorded sizes,
checks and limitations. Validate your production models on the target CPU.

This repository is licensed under [BSD-3-Clause](LICENSE). Bundled components
retain their own licenses and notices.
