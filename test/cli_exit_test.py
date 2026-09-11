"""Check CLI exit precedence with synthetic workflows: python3 test/cli_exit_test.py."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def output_digest():
    payload = [False, [[6, hashlib.sha256(b"actual").hexdigest()]]]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


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
                self.assertIn(output_digest(), history.read_text())

    def test_inprocess_api_preserves_reference_failure(self):
        self.assert_exit(self.run_workflow("import sys\nsys.exit(0)\n",
                                          reference="0" * 64, inprocess=True), 73)

    def test_successful_checks_preserve_workflow_exit(self):
        reference = output_digest()
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

    def assert_history_retained(self):
        history = self.root / "logs/jawm_hashes/workflow_user_defined.history"
        self.assertIn(output_digest(), history.read_text())

    def test_child_failure_without_explicit_wait_fails_after_hashing(self):
        result = self.run_workflow(
            "from jawm import Process\nimport sys\n"
            "Process(name='failed_child', script='#!/bin/sh\\nexit 7\\n').execute()\n"
            "sys.exit(0)\n")
        self.assert_exit(result, 1)
        self.assert_history_retained()
        codes = list((self.root / "logs").glob("*/failed_child.exitcode"))
        self.assertEqual(len(codes), 1)
        self.assertEqual(codes[0].read_text().strip(), "7")

    def test_reference_failure_takes_precedence_over_child_failure(self):
        result = self.run_workflow(
            "from jawm import Process\n"
            "Process(name='failed_child', script='#!/bin/sh\\nexit 7\\n').execute()\n",
            reference="0" * 64)
        self.assert_exit(result, 73)
        self.assert_history_retained()

    def test_failed_upstream_blocks_downstream_without_workflow_exit(self):
        result = self.run_workflow(
            "from jawm import Process\n"
            "Process(name='upstream', parallel=False, script='#!/bin/sh\\nexit 7\\n').execute()\n"
            "Process(name='downstream', depends_on=['upstream'], "
            "script='#!/bin/sh\\ntouch should_not_exist\\n').execute()\n")
        self.assert_exit(result, 1)
        self.assertFalse((self.root / "should_not_exist").exists())
        self.assertIn("downstream", result.stdout + result.stderr)
        self.assert_history_retained()

    def test_successful_child_and_intentional_skip_pass(self):
        result = self.run_workflow(
            "from jawm import Process\n"
            "Process(name='success', script='#!/bin/sh\\nexit 0\\n').execute()\n"
            "Process(name='intentional_skip', when=lambda: False).execute()\n")
        self.assert_exit(result, 0)

    def test_strict_dependency_block_is_not_an_intentional_skip(self):
        for detached in (False, True):
            with self.subTest(detached=detached):
                result = self.run_workflow(
                    "from jawm import Process\n"
                    "Process(name='skipped', when=False).execute()\n"
                    "Process(name='blocked', depends_on=['skipped'], allow_skipped_deps=False, "
                    "parallel=False, run_in_detached=%r).execute()\n" % detached)
                self.assert_exit(result, 1)
                self.assertIn("blocked", result.stdout + result.stderr)
                self.assert_history_retained()

    def test_wait_exception_fails_after_hashing(self):
        result = self.run_workflow(
            "from jawm import Process\nimport sys\n"
            "def broken_wait(cls, *args, **kwargs):\n"
            "    raise RuntimeError('synthetic wait failure')\n"
            "Process.wait = classmethod(broken_wait)\n"
            "sys.exit(0)\n")
        self.assert_exit(result, 1)
        self.assert_history_retained()

    def test_wait_timeout_remains_failure_after_child_finishes(self):
        self.env.update({"JAWM_WAIT_STABILIZE": "0", "JAWM_WAIT_TIMEOUT": "0"})
        result = self.run_workflow(
            "from jawm import Process\n"
            "Process(name='slow', script='#!/bin/sh\\nsleep 1\\n').execute()\n")
        self.assert_exit(result, 1)
        self.assert_history_retained()

    def test_successful_retry_passes(self):
        result = self.run_workflow(
            "from jawm import Process\n"
            "Process(name='retry', retries=1, script='#!/bin/sh\\n"
            "if [ ! -f attempted ]; then touch attempted; exit 7; fi\\nexit 0\\n').execute()\n")
        self.assert_exit(result, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
