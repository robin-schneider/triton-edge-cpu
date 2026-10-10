"""Pure Python child model for BLS, independent of framework backends."""
import numpy as np
import triton_python_backend_utils as pb_utils


class TritonPythonModel:
    def execute(self, requests):
        responses = []
        for request in requests:
            x = pb_utils.get_input_tensor_by_name(request, 'INPUT').as_numpy()
            result = (x + x).astype(np.float32)
            responses.append(pb_utils.InferenceResponse(output_tensors=[pb_utils.Tensor('OUTPUT', result)]))
        return responses
