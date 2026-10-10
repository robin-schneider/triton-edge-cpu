"""BLS composition with custom Prometheus metrics and propagated errors."""
import numpy as np
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    def initialize(self, args):
        self.families = {}
        self.metrics = {}
        for suffix in ('requests', 'errors'):
            family = pb_utils.MetricFamily(
                name=f'edge_bls_{suffix}_total',
                description=f'BLS {suffix} observed by the Python model',
                kind=pb_utils.MetricFamily.COUNTER,
            )
            self.families[suffix] = family
            self.metrics[suffix] = family.Metric(labels={'model': args['model_name'], 'version': args['model_version']})

    def execute(self, requests):
        responses = []
        for request in requests:
            self.metrics['requests'].increment(1)
            x = pb_utils.get_input_tensor_by_name(request, 'INPUT').as_numpy()
            # Negative input exercises downstream error propagation in tests.
            target = 'missing_bls_child' if np.any(x < 0) else 'smoke_python_child'
            child = pb_utils.InferenceRequest(
                model_name=target,
                requested_output_names=['OUTPUT'],
                inputs=[pb_utils.Tensor('INPUT', x)],
            ).exec()
            if child.has_error():
                self.metrics['errors'].increment(1)
                responses.append(pb_utils.InferenceResponse(error=child.error()))
            else:
                y = pb_utils.get_output_tensor_by_name(child, 'OUTPUT').as_numpy()
                responses.append(pb_utils.InferenceResponse(output_tensors=[pb_utils.Tensor('OUTPUT', y + 1)]))
        return responses

    def finalize(self):
        # Metrics must be destroyed before their owning MetricFamilies.
        self.metrics.clear()
        self.families.clear()
