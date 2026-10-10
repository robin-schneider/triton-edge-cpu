"""Read a Docker filesystem export and attribute actual file bytes once.

Runs in Dockerfile.tooling, using its Docker CLI and Python standard library.
It does not install anything into the host or production image.
"""
import collections
import csv
import json
from pathlib import Path
import subprocess
import sys
import tarfile

image, output = sys.argv[1:]
output = Path(output)
output.mkdir(parents=True, exist_ok=True)
metadata = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
container = subprocess.check_output(['docker', 'create', image], text=True).strip()
files = {}
owners = {}
try:
    process = subprocess.Popen(['docker', 'export', container], stdout=subprocess.PIPE)
    with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
        for member in archive:
            path = '/' + member.name.removeprefix('./').lstrip('/')
            if not member.isfile():
                continue
            files[path] = member.size
            if path.startswith('/var/lib/dpkg/info/') and path.endswith('.list'):
                package = Path(path).name[:-5].split(':')[0]
                for entry in archive.extractfile(member).read().decode().splitlines():
                    if entry.startswith(('/lib/', '/lib64/', '/bin/', '/sbin/')):
                        entry = '/usr' + entry
                    owners[entry] = package
    if process.wait() != 0:
        raise RuntimeError('docker export failed')
finally:
    subprocess.run(['docker', 'rm', container], check=True, stdout=subprocess.DEVNULL)

def dependency(path):
    name = Path(path).name
    if path.startswith('/opt/tritonserver/backends/python/'):
        return 'Python backend and stub'
    if path.startswith('/usr/lib/python3.12/'):
        return 'Python 3.12 standard library'
    if path.startswith('/usr/lib/python3/dist-packages/numpy'):
        return 'NumPy'
    if name.startswith('libpython3.12') or path == '/usr/bin/python3.12':
        return 'Python 3.12 interpreter and shared runtime'
    if path.startswith('/opt/tritonserver/backends/pytorch/'):
        if name.startswith(('libmkl', 'libiomp')):
            return 'Intel MKL / OpenMP (PyTorch)'
        if name.startswith(('libtorch_cuda', 'libtorch_nvshmem', 'libc10_cuda')):
            return 'PyTorch CUDA-linked libraries'
        if name.startswith('libtorch_cpu'):
            return 'PyTorch CPU library'
        return 'PyTorch backend and other bundled libraries'
    if path.startswith('/opt/tritonserver/backends/openvino/'):
        if 'intel_cpu_plugin' in name:
            return 'OpenVINO CPU plugin'
        if '_frontend.so' in name:
            return 'OpenVINO model-format frontends'
        return 'OpenVINO core, TBB, backend and dispatch plugins'
    if path.startswith('/opt/tritonserver/backends/onnxruntime/'):
        if name in ('onnx_test_runner', 'onnxruntime_perf_test'):
            return 'ONNX Runtime test / benchmark executables'
        return 'ONNX Runtime and backend'
    if path.startswith('/usr/local/cuda/'):
        if name.startswith('libcusparseLt'):
            return 'NVIDIA cuSPARSELt'
        if name.startswith('libnvrtc'):
            return 'NVIDIA NVRTC'
        return 'Other NVIDIA CUDA runtimes / stubs'
    if name.startswith('libnccl'):
        return 'NVIDIA NCCL'
    if name.startswith('libcudnn'):
        return 'NVIDIA cuDNN'
    if path.startswith('/opt/hpcx/'):
        return 'HPC-X UCX / UCC libraries'
    if path.startswith(('/opt/tritonserver/bin/', '/opt/tritonserver/lib/')):
        return 'Triton server executable and core library'
    if path.startswith('/usr/share/doc/') or path.endswith('.pdf'):
        return 'License notices and packaged documentation'
    if path in owners:
        return 'Ubuntu package: ' + owners[path]
    if path.startswith(('/usr/lib/', '/usr/local/lib/')) and '.so' in name:
        return 'Copied runtime library: ' + name
    return 'Other OS files, certificates and package metadata'

groups = collections.Counter()
packages = collections.Counter()
with (output / 'image-files.csv').open('w') as stream:
    writer = csv.writer(stream)
    writer.writerow(['path', 'file_bytes', 'dependency', 'dpkg_owner'])
    for path, size in sorted(files.items()):
        group = dependency(path)
        groups[group] += size
        if path in owners:
            packages[owners[path]] += size
        writer.writerow([path, size, group, owners.get(path, '')])
with (output / 'package-files.csv').open('w') as stream:
    writer = csv.writer(stream)
    writer.writerow(['package', 'owned_file_bytes'])
    writer.writerows(packages.most_common())

# Keep every large dependency visible, aggregate small OS packages/libraries.
summary = collections.Counter()
for group, size in groups.items():
    if group.startswith(('Ubuntu package:', 'Copied runtime library:')) and size < 2_000_000:
        group = 'Other small Ubuntu packages and copied system libraries'
    summary[group] += size
payload = sum(files.values())
summary['Layer / archive overhead and overwritten files'] = metadata['Size'] - payload
lines = [f"Measured image: `{image}` (`{metadata['Id']}`).", '',
         '| Installed dependency / component | MB (decimal) | Share of image |',
         '| --- | ---: | ---: |']
for group, size in summary.most_common():
    lines.append(f'| {group} | {size / 1e6:,.2f} | {size / metadata["Size"]:.1%} |')
lines.append(f'| **Total uncompressed Docker image** | **{metadata["Size"] / 1e6:,.2f}** | **100%** |')
(output / 'image-size.md').write_text('\n'.join(lines) + '\n')
(output / 'image-size.json').write_text(json.dumps({'image': image, 'id': metadata['Id'],
    'docker_bytes': metadata['Size'], 'regular_file_bytes': payload,
    'dependencies': dict(groups)}, indent=2) + '\n')
print('\n'.join(lines))
