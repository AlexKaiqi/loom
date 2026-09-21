"""Installer failure boundaries that do not require a working Docker engine."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Prerequisites(unittest.TestCase):
    def test_unresponsive_engine_is_bounded_and_does_not_create_installation(self):
        with tempfile.TemporaryDirectory(prefix='loom-install-prerequisite-') as temporary:
            root = Path(temporary)
            tools = root / 'tools'
            tools.mkdir()
            docker = tools / 'docker'
            docker.write_text('#!' + sys.executable + '\nimport time\ntime.sleep(90)\n')
            docker.chmod(0o755)
            prefix = root / 'installation'
            workspace = root / 'workspace'
            started = time.monotonic()
            result = subprocess.run([sys.executable, str(ROOT/'scripts/install.py'), '--deployment', 'docker', '--prefix', str(prefix),
                '--workspace-root', str(workspace)], capture_output=True, text=True, timeout=25,
                env=dict(os.environ, PATH=str(tools)+os.pathsep+os.environ.get('PATH', '')))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Docker engine did not respond within 15 seconds', result.stderr)
            self.assertNotIn('Traceback', result.stderr)
            self.assertLess(time.monotonic()-started, 22)
            self.assertFalse(prefix.exists())
            self.assertFalse(workspace.exists())


if __name__ == '__main__':
    unittest.main()
