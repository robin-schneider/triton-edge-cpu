#!/usr/bin/env python3
"""Apply reviewed download-policy changes to a staged backend, never its lock checkout."""
from pathlib import Path
import os
import sys

name=sys.argv[1]
root=Path(name)
script={'onnxruntime':'gen_ort_dockerfile.py','openvino':'gen_openvino_dockerfile.py'}.get(name)
if script:
    generator=root/'tools'/script
    with generator.open('a') as f:
        f.write('\n# Downstream: consume only inputs acquired before compilation.\n')
        f.write('import runpy\nrunpy.run_path("/workspace/.cpu-build/lock-framework.py", '+
                'init_globals={"output": FLAGS.output, "environment": '+repr(name)+'})\n')
    cmake=root/'CMakeLists.txt'
    text=cmake.read_text()
    flags='--network=none'+(' --no-cache' if os.environ.get('CLEAN_BUILD')=='1' else '')
    text=text.replace('COMMAND docker build ', 'COMMAND docker build '+flags+' ')
    cmake.write_text(text)
