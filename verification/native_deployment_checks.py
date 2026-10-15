"""Native release update retains old binary and rejects stale builds."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import install_local_roles as installer


class Checks(unittest.TestCase):
    def test_versioned_native_update_and_source_binding(self):
        with tempfile.TemporaryDirectory() as temporary:
            base=Path(temporary);project=base/'project';opt=base/'opt'
            (project/'build').mkdir(parents=True);(project/'src').mkdir();(project/'scripts').mkdir()
            source=project/'src/he_bridge.cpp';script=project/'scripts/build_stage3.sh';binary=project/'build/he_bridge'
            source.write_text('native version one');script.write_text('build recipe');binary.write_bytes(b'binary-one')
            def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
            def record():
                value=dict(source_sha256=digest(source),script_sha256=digest(script),binary_sha256=digest(binary))
                (project/'build/he_bridge-build.json').write_text(json.dumps(value));return value
            def mkdir(path,uid=0,gid=0,mode=0o700):Path(path).mkdir(parents=True,exist_ok=True)
            with patch.object(installer,'PROJECT',project),patch.object(installer,'OPT',opt),\
                 patch.object(installer,'secure_dir',side_effect=mkdir),patch.object(installer.os,'chown'):
                first=record();self.assertEqual(installer.native_build(),first)
                self.assertEqual(installer.install_native(first),first['binary_sha256'])
                target=opt/'native/build/he_bridge';self.assertEqual(target.read_bytes(),b'binary-one')
                source.write_text('native version two');binary.write_bytes(b'binary-two')
                with self.assertRaisesRegex(RuntimeError,'NATIVE_BUILD_SOURCE_MISMATCH'):installer.native_build()
                second=record();self.assertEqual(installer.install_native(second),second['binary_sha256'])
                self.assertEqual(target.read_bytes(),b'binary-two')
                self.assertEqual((opt/'native/releases'/first['binary_sha256']/'he_bridge').read_bytes(),b'binary-one')
                self.assertEqual(installer.install_native(second),second['binary_sha256'])


if __name__=='__main__':unittest.main()
