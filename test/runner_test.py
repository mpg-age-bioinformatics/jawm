"""Regression tests for jawm-test's current-run output comparison.

Run with: python3 test/runner_test.py
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
