"""Regression tests for jawm-test output comparison and jawm CLI exits.

Run with: python3 test/cli_regression_test.py
Uses the checkout and synthetic files, without installs or remote services.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


def digest(value):
    data = value.encode()
    payload = [False, [[len(data), hashlib.sha256(data).hexdigest()]]]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jawm_runner_test_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "test").mkdir()
        (self.root / "bin").mkdir()
        self.launcher = self.root / "bin" / "jawm"
        self.launcher.write_text(
            "#!/bin/sh\nexec " + shlex.quote(sys.executable) + ' -m jawm.cli "$@"\n'
        )
        self.launcher.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("JAWM_")}
        self.env.update({
            "PATH": str(self.root / "bin") + os.pathsep + os.environ["PATH"],
            "PYTHONPATH": str(REPO),
            "PYTHONDONTWRITEBYTECODE": "1",
            "JAWM_CONFIG_FILE": "/dev/null",
            "JAWM_MONITORING_DIRECTORY": str(self.root / "monitoring"),
        })
        (self.root / "workflow.py").write_text(
            "from pathlib import Path\n"
            "Path('output.txt').write_text(Path('input.txt').read_text())\n"
        )
        (self.root / "input.txt").write_text("baseline")
        self.params = self.root / "params.yaml"
        self.params.write_text("- scope: hash\n  include: [output.txt]\n  overwrite: false\n")
        self.tests_file = self.root / "test" / "tests.txt"
        self.write_tests(digest("baseline"))

    def write_tests(self, expected):
        self.tests_file.write_text(
            '# module;workflow;params;name;hash\n'
            'workflow.py;main;params.yaml;"output";' + expected + '\n'
        )

    def run_runner(self, *args):
        return subprocess.run(
            ["/bin/bash", "-e", str(REPO / "jawm/data/jawm-test"),
             "--module_versions", "current", "--jawm_repo", str(REPO), *args],
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=60,
        )

    def assert_rc(self, result, expected):
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_changed_output_fails_with_preserved_baselines(self):
        # Reproduce the legacy shared hash as well as a previous test invocation.
        legacy = self.root / "test/logs/jawm_hashes/workflow.hash"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(digest("baseline") + "\n")
        self.assert_rc(self.run_runner(), 0)
        original_tests = self.tests_file.read_text()
        (self.root / "input.txt").write_text("changed")
        changed = self.run_runner()
        self.assert_rc(changed, 1)
        self.assertIn("Hashes do not match! Test failed.", changed.stdout)
        self.assertEqual(self.tests_file.read_text(), original_tests)
        self.assertEqual(legacy.read_text().strip(), digest("baseline"))
        hashes = list((self.root / "test/logs").glob("run.*/jawm_hashes/workflow.hash"))
        self.assertEqual(len(hashes), 2)
        self.assertEqual({p.read_text().strip() for p in hashes},
                         {digest("baseline"), digest("changed")})

    def test_unchanged_output_passes_repeatedly(self):
        self.assert_rc(self.run_runner(), 0)
        self.assert_rc(self.run_runner(), 0)

    def test_override_accepts_current_output(self):
        self.assert_rc(self.run_runner(), 0)
        (self.root / "input.txt").write_text("changed")
        self.assert_rc(self.run_runner("--override"), 0)
        self.assertIn(digest("changed"), self.tests_file.read_text())
        self.assert_rc(self.run_runner(), 0)

    def test_empty_expected_hash_captures_current_output(self):
        self.assert_rc(self.run_runner(), 0)
        self.write_tests("")
        (self.root / "input.txt").write_text("changed")
        self.assert_rc(self.run_runner(), 0)
        self.assertIn(digest("changed"), self.tests_file.read_text())

    def test_repeated_module_rows_have_independent_hashes(self):
        (self.root / "other.txt").write_text("other")
        (self.root / "other.yaml").write_text(
            "- scope: hash\n  include: [other.txt]\n  overwrite: false\n"
        )
        with self.tests_file.open("a") as f:
            f.write('workflow.py;main;other.yaml;"other";' + digest("other") + '\n')
        self.assert_rc(self.run_runner(), 0)

    def test_missing_hash_cannot_reuse_previous_result_even_with_override(self):
        self.assert_rc(self.run_runner(), 0)
        original_tests = self.tests_file.read_text()
        self.params.write_text("[]\n")
        result = self.run_runner("--override")
        self.assert_rc(result, 1)
        self.assertIn("missing or malformed current-run", result.stdout)
        self.assertEqual(self.tests_file.read_text(), original_tests)

    def test_ignore_retains_failed_rows_and_continues(self):
        self.params.write_text("[]\n")
        (self.root / "good.yaml").write_text("- scope: hash\n  include: [output.txt]\n")
        with self.tests_file.open("a") as f:
            f.write('workflow.py;main;good.yaml;"good";' + digest("baseline") + '\n')
        original_tests = self.tests_file.read_text()
        result = self.run_runner("--ignore")
        self.assert_rc(result, 0)
        self.assertIn("missing or malformed current-run", result.stdout)
        self.assertIn("Generated HASH: " + digest("baseline"), result.stdout)
        self.assertEqual(self.tests_file.read_text(), original_tests)

    def test_malformed_current_hash_is_rejected(self):
        # Exercise the runner boundary with a CLI reporting success but bad evidence.
        writer = self.root / "bad_hash.py"
        writer.write_text(
            "from pathlib import Path\nimport sys\n"
            "p = Path(sys.argv[sys.argv.index('-l') + 1]) / 'jawm_hashes'\n"
            "p.mkdir()\n(p / 'workflow.hash').write_text('not-a-sha256\\n')\n"
        )
        self.launcher.write_text("#!/bin/sh\nexec " + shlex.quote(sys.executable)
                                 + " " + shlex.quote(str(writer)) + ' "$@"\n')
        original_tests = self.tests_file.read_text()
        result = self.run_runner()
        self.assert_rc(result, 1)
        self.assertIn("missing or malformed current-run", result.stdout)
        self.assertEqual(self.tests_file.read_text(), original_tests)


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
