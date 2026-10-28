# Locked inputs and clean builds

Run `./triton build --clean` for a build with no cached Docker RUN layers or
reused compiler output. `./triton --clean` also runs inference acceptance tests
and collects provenance. Inputs already downloaded are reused only after their
checksums and Git revisions have been verified; deleting `.work/sources` and
`.work/inputs` forces fresh acquisition.

The entry point first fetches Git dependencies using `git init` and
`git fetch --depth=1 --no-tags URL COMMIT`. It records no remote branch heads.
Bootstrap then validates detached checkouts and recursively initializes modules
through local mirrors containing only the locked commits. During compilation,
Git's only allowed transport is `file`; an undeclared dependency fails instead
of fetching another source version.

The checked-in locks preserve the previous local build's versions:

| Lock | Inputs |
| --- | --- |
| `config/sources.lock.json` | 96 exact Git commits, including recursive modules and Python backend dependencies |
| `config/images.lock.json` | 9 digest-pinned images, exclusively Docker Hub and NGC |
| `config/locks/*.apt.json` | Exact package versions, artifact URLs and SHA-256 hashes; Ubuntu snapshot dated 2026-10-09 |
| `config/locks/*.wheels.json` | Original concrete wheel artifacts, installed platform tags and SHA-256 hashes |
| `config/archives.lock.json` | 23 source/binary release archives with SHA-256 hashes |
| `config/locks/*.packages.txt`, `*.pypi.json` | Original package inventories used to construct the locks |

Keep the entire checked-in project to rebuild. `config/locks/` alone is not a
complete bundle: the other lock JSON files and `config/build.env` sit directly
under `config/`, and the Dockerfiles, scripts and patch define how those inputs
are built. The original `*.pip.json`, `*.pypi.json`, `*.packages.txt` and
`baseline-images.json` files provide audit evidence; the `*.apt.json` and
`*.wheels.json` files select the actual package artifacts. Generated `.work/`
caches and `artifacts/` reports do not need to be checked into Git.

The first acquisition stage also stages source archives from GitHub/Boost and
the original Intel TBB release artifact. This preserves the existing TBB binary;
the similarly versioned PyPI wheel contains different bytes. The build stages
consume local verified artifacts and cannot contact these servers. Python
packages come from PyPI or the official PyTorch wheel repository. No images are
published or downloaded from custom OCI registries.

Dependency images are built locally from the public digest-pinned bases.
Wheel metadata is checked as well as hashes: a generic wheel cannot silently
replace a native wheel with the same package version. This matters for Triton
client shared-memory support and accelerated Protobuf.

The original intermediate SDK/OpenAI packages are preserved at their installed
versions, and the two Triton SDK wheels come from the locked source build.
Packages install from a file-only apt repository and hash-locked wheelhouses;
only declared files enter its apt repository and wheelhouses, so stale cache
contents cannot affect an isolated build. There is no live package solver or
implicit PEP 517 download during compilation.
NVIDIA's PyTorch and Triton-min images still supply the same precompiled runtime
libraries as before. ONNX Runtime, OpenVINO, Triton and the Python backend are
compiled from the staged locked sources.

`./scripts/check-source-lock.sh` verifies the complete cached input closure
without remote branch queries. A dirty source, missing module, changed local
ref, missing package or checksum mismatch fails the build. Updating dependencies
requires reviewing and updating the locks together and clearing the old source
cache. Undeclared cached Git refs/history are rejected. There is no fallback to a
newer version when a historical artifact disappears.

`--reuse-artifacts` requires a receipt matching both the current recipe/input
fingerprint and the exact local core/buildbase image IDs. It cannot silently
reuse artifacts from before the dependency locks were introduced.

The original OpenVINO build number and ONNX Runtime branch/commit label are
recorded explicitly in `config/build.env`; shallow checkouts do not need full
history to reproduce those version strings. A fixed source timestamp is passed
into compiler stages. The deployable image is packaged as a canonical filesystem layer and Docker
configuration: entries are sorted, timestamps use the source epoch, transient
logs/caches and machine IDs are omitted, and account age fields are normalized.
This removes dependency-image creation times from the deployed image identity.
Build caches remain available for intermediate compiler images. Generated
recipes and input receipts are retained outside the runtime image for auditing.

Compare final image IDs across independent clean builds to verify the complete
compiler pipeline, in addition to input integrity and deterministic packaging.
The packaging regression check uses independent uncached builds with varying
log data and timestamps, and verifies identical image IDs and preserved payload.

`config/locks/baseline-images.json` records the original local audit images.
Those local image IDs are provenance; they are not registry inputs or images
that another builder must possess.
