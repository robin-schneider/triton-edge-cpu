"""Verify TLS inference, observability and actual POSIX shared-memory reads."""
import json
import os
import re
import ssl
import urllib.request
import numpy as np
import tritonclient.http as http
import tritonclient.grpc as grpc
import tritonclient.utils.shared_memory as shm
from tritonclient.utils import InferenceServerException

context = ssl.create_default_context(cafile='/certs/ca.crt')
http_client = http.InferenceServerClient('gateway:8443', ssl=True, ssl_context_factory=lambda: context)
grpc_client = grpc.InferenceServerClient('gateway:8444', ssl=True, root_certificates='/certs/ca.crt')
x = np.arange(4, dtype=np.float32)
models = os.environ.get('SMOKE_MODELS', 'smoke_pytorch,smoke_onnx,smoke_openvino').split(',')

def read_metrics():
    with urllib.request.urlopen('https://gateway:8443/metrics', context=context) as response:
        return response.read().decode()

def metric_value(text, name):
    values = re.findall(r'^' + re.escape(name) + r'(?:\{[^\n]*\})?\s+([0-9.eE+-]+)$', text, re.MULTILINE)
    assert len(values) == 1, f'Expected one custom metric {name}, got {values}'
    return float(values[0])

baseline = read_metrics() if 'smoke_bls' in models else ''
bls_calls = 0
for client, module in [(http_client, http), (grpc_client, grpc)]:
    assert client.is_server_live() and client.is_server_ready()
    for model in models:
        input_name, output_name = ('INPUT__0', 'OUTPUT__0') if model == 'smoke_pytorch' else ('INPUT', 'OUTPUT')
        inp = module.InferInput(input_name, [4], 'FP32')
        inp.set_data_from_numpy(x)
        result = client.infer(model, [inp])
        expected = x * 2 + 1 if model == 'smoke_bls' else x * 2
        np.testing.assert_array_equal(result.as_numpy(output_name), expected)
        bls_calls += model == 'smoke_bls'
        print(f'{module.__name__}: {model} inference passed')

handle = shm.create_shared_memory_region('cpu_smoke', '/cpu_smoke', x.nbytes)
try:
    shm.set_shared_memory_region(handle, [x])
    http_client.register_system_shared_memory('cpu_smoke', '/cpu_smoke', x.nbytes)
    model = models[0]
    input_name, output_name = ('INPUT__0', 'OUTPUT__0') if model == 'smoke_pytorch' else ('INPUT', 'OUTPUT')
    inp = http.InferInput(input_name, [4], 'FP32')
    inp.set_shared_memory('cpu_smoke', x.nbytes)
    expected = x * 2 + 1 if model == 'smoke_bls' else x * 2
    np.testing.assert_array_equal(http_client.infer(model, [inp]).as_numpy(output_name), expected)
    bls_calls += model == 'smoke_bls'
    print('POSIX shared-memory inference passed')
finally:
    try:
        http_client.unregister_system_shared_memory('cpu_smoke')
    finally:
        shm.destroy_shared_memory_region(handle)
for path in (f'/v2/models/{models[0]}/stats', '/v2/trace/setting', '/v2/logging'):
    with urllib.request.urlopen('https://gateway:8443' + path, context=context) as response:
        assert json.load(response)
if 'smoke_bls' in models:
    for client, module in [(http_client, http), (grpc_client, grpc)]:
        inp = module.InferInput('INPUT', [4], 'FP32')
        inp.set_data_from_numpy(-np.ones(4, dtype=np.float32))
        try:
            client.infer('smoke_bls', [inp])
        except InferenceServerException as error:
            assert 'missing_bls_child' in str(error)
        else:
            raise AssertionError('BLS must propagate a failed child request')
        bls_calls += 1
    metrics = read_metrics()
    assert metric_value(metrics, 'edge_bls_requests_total') - metric_value(baseline, 'edge_bls_requests_total') == bls_calls
    assert metric_value(metrics, 'edge_bls_errors_total') - metric_value(baseline, 'edge_bls_errors_total') == 2
    print('Python BLS composition, downstream errors and custom metric counter deltas passed')
metrics = read_metrics()
assert 'nv_inference_request_success' in metrics
assert 'nv_cpu_utilization' in metrics
print('Metrics, statistics, tracing and logging endpoints passed')
