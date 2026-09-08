"""Check CLI exit precedence with synthetic workflows: python3 test/cli_exit_test.py."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class CliExitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jawm_cli_exit_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("JAWM_")}
        self.env.update({
            "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1",
            "JAWM_CONFIG_FILE": "/dev/null",
            "JAWM_MONITORING_DIRECTORY": str(self.root / "monitoring"),
        })
        (self.root / "output.txt").write_text("actual")

    def run_workflow(self, script, reference=None, include="output.txt", inprocess=False):
        (self.root / "workflow.py").write_text(script)
        config = "- scope: hash\n  include: [" + include + "]\n"
        if reference is not None:
            config += "  reference: '" + reference + "'\n"
        (self.root / "params.yaml").write_text(config)
        args = ["workflow.py", "-p", "params.yaml"]
        command = [sys.executable, "-m", "jawm.cli"]
        if inprocess:
            command = [sys.executable, "-c",
                       "import sys; from jawm.cli import run; "
                       "sys.exit(run(sys.argv[1:], inprocess=True))"]
        return subprocess.run(command + args, cwd=self.root, env=self.env,
                              text=True, capture_output=True, timeout=45)

    def assert_exit(self, result, expected):
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        ending = [line for line in (result.stdout + result.stderr).splitlines()
                  if "Ending jawm module script from jawm command" in line]
        self.assertTrue(ending)
        if expected:
            self.assertIn("with exit code " + str(expected), ending[-1])

    def test_reference_mismatch_overrides_workflow_exit(self):
        for requested in (0, 7):
            with self.subTest(requested=requested):
                result = self.run_workflow("import sys\nsys.exit(%d)\n" % requested,
                                           reference="0" * 64)
                self.assert_exit(result, 73)
                self.assertIn("does NOT match reference", result.stdout + result.stderr)
                history = self.root / "logs/jawm_hashes/workflow_user_defined.history"
                self.assertIn(hashlib.sha256(b"actual").hexdigest(), history.read_text())

    def test_inprocess_api_preserves_reference_failure(self):
        self.assert_exit(self.run_workflow("import sys\nsys.exit(0)\n",
                                          reference="0" * 64, inprocess=True), 73)

    def test_successful_checks_preserve_workflow_exit(self):
        reference = hashlib.sha256(b"actual").hexdigest()
        for script, expected in [("pass\n", 0), ("import sys\nsys.exit(0)\n", 0),
                                 ("import sys\nsys.exit()\n", 0),
                                 ("import sys\nsys.exit(7)\n", 7),
                                 ("import sys\nsys.exit('workflow failed')\n", 1)]:
            with self.subTest(script=script):
                self.assert_exit(self.run_workflow(script, reference=reference), expected)

    def test_invalid_reference_cannot_be_masked(self):
        self.assert_exit(self.run_workflow("import sys\nsys.exit(0)\n",
                                          reference="sha256:invalid"), 73)

    def test_missing_hash_input_cannot_be_masked(self):
        self.assert_exit(self.run_workflow("import sys\nsys.exit(0)\n",
                                          include="missing.txt"), 73)

    def test_post_run_exception_cannot_be_masked(self):
        # A directory at the expected hash-file path causes an actual I/O failure.
        script = ("from pathlib import Path\nimport sys\n"
                  "Path('logs/jawm_hashes/workflow.hash').mkdir(parents=True)\n"
                  "sys.exit(0)\n")
        self.assert_exit(self.run_workflow(script), 1)

    def test_workflow_exception_still_fails(self):
        self.assert_exit(self.run_workflow("raise RuntimeError('workflow failed')\n"), 1)

    def test_mismatch_without_reference_remains_informational(self):
        self.assert_exit(self.run_workflow("pass\n"), 0)
        (self.root / "output.txt").write_text("changed")
        result = self.run_workflow("import sys\nsys.exit(0)\n")
        self.assert_exit(result, 0)
        self.assertIn("STATUS: MISMATCHED", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
