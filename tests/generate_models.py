"""Create tiny deterministic CPU models inside the disposable test image."""
from pathlib import Path
import shutil
import numpy as np
import onnx
from onnx import TensorProto, helper
import openvino as ov
from openvino import opset13 as ops
import torch

root = Path('/models')
for name, backend in [('smoke_pytorch', 'pytorch'), ('smoke_onnx', 'onnxruntime'), ('smoke_openvino', 'openvino')]:
    directory = root / name / '1'
    directory.mkdir(parents=True, exist_ok=True)
    input_name, output_name = ('INPUT__0', 'OUTPUT__0') if backend == 'pytorch' else ('INPUT', 'OUTPUT')
    (directory.parent / 'config.pbtxt').write_text(f'''name: "{name}"
backend: "{backend}"
max_batch_size: 0
input [{{name: "{input_name}" data_type: TYPE_FP32 dims: [4]}}]
output [{{name: "{output_name}" data_type: TYPE_FP32 dims: [4]}}]
instance_group [{{kind: KIND_CPU count: 1}}]
''')
    if backend == 'pytorch':
        class Twice(torch.nn.Module):
            def forward(self, x):
                return x + x
        torch.jit.trace(Twice().eval(), torch.ones(4)).save(str(directory / 'model.pt'))
    elif backend == 'onnxruntime':
        graph = helper.make_graph([helper.make_node('Add', ['INPUT', 'INPUT'], ['OUTPUT'])], 'twice',
                                  [helper.make_tensor_value_info('INPUT', TensorProto.FLOAT, [4])],
                                  [helper.make_tensor_value_info('OUTPUT', TensorProto.FLOAT, [4])])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 13)], ir_version=10)
        onnx.checker.check_model(model)
        onnx.save(model, directory / 'model.onnx')
    else:
        parameter = ops.parameter([4], np.float32, name='INPUT')
        parameter.output(0).get_tensor().set_names({'INPUT'})
        result = ops.add(parameter, parameter)
        result.output(0).get_tensor().set_names({'OUTPUT'})
        ov.serialize(ov.Model([result], [parameter], 'twice'), directory / 'model.xml', directory / 'model.bin')
for name, script in [('smoke_python_child', 'child.py'), ('smoke_bls', 'model.py')]:
    directory = root / name / '1'
    directory.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path('/tests/bls') / script, directory / 'model.py')
    (directory.parent / 'config.pbtxt').write_text(f'''name: "{name}"
backend: "python"
max_batch_size: 0
input [{{name: "INPUT" data_type: TYPE_FP32 dims: [4]}}]
output [{{name: "OUTPUT" data_type: TYPE_FP32 dims: [4]}}]
instance_group [{{kind: KIND_CPU count: 1}}]
''')
print('Generated framework and Python BLS test models.')
