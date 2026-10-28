"""Checks for the build's integrity boundaries (no network required)."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from inputs import fetch
from sources import manifest


class InputIntegrityTests(unittest.TestCase):
    def test_cached_inputs_are_verified_before_use(self):
        with tempfile.TemporaryDirectory() as folder:
            artifact=Path(folder)/'package.whl'
            artifact.write_bytes(b'locked artifact')
            row={'url':'https://files.pythonhosted.org/example.whl',
                 'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest()}
            with patch('urllib.request.urlopen', side_effect=AssertionError('Unexpected network')):
                fetch(row, artifact, verify=True)
                artifact.write_bytes(b'corrupt cache')
                with self.assertRaisesRegex(ValueError, 'modified locked input'):
                    fetch(row, artifact, verify=True)

    def test_generic_wheel_cannot_replace_native_wheel_at_same_version(self):
        with tempfile.TemporaryDirectory() as folder:
            artifact=Path(folder)/'client.whl'
            with zipfile.ZipFile(artifact,'w') as wheel:
                wheel.writestr('client-1.0.dist-info/METADATA','Name: client\nVersion: 1.0\n')
                wheel.writestr('client-1.0.dist-info/WHEEL','Wheel-Version: 1.0\nTag: py3-none-any\n')
            row={'url':'https://files.pythonhosted.org/client.whl','name':'client','version':'1.0',
                 'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(),
                 'wheel_tags':['py3-none-manylinux1_x86_64']}
            with self.assertRaisesRegex(ValueError,'Wheel identity/platform'):
                fetch(row,artifact,verify=True)

    def test_moving_reference_cannot_select_two_commits(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lock.json'
            rows=[dict(id='one',url='https://github.com/example/project.git',
                       commit='a'*40,refs=['refs/heads/release']),
                  dict(id='two',url='https://github.com/example/project',
                       commit='b'*40,refs=['refs/heads/release'])]
            path.write_text(json.dumps({'repositories':rows}))
            with self.assertRaisesRegex(ValueError, 'Ambiguous locked reference'):
                manifest(path)

    def test_ref_names_cannot_replace_commit_locks(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lock.json'
            path.write_text(json.dumps({'repositories':[
                dict(id='project',url='https://github.com/example/project.git',commit='main')]}))
            with self.assertRaisesRegex(ValueError, 'Invalid/duplicate source lock'):
                manifest(path)


if __name__=='__main__':
    unittest.main()
