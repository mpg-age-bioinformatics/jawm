"""Retry record regression tests: python test/retry_records_test.py."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class RetryRecordsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jawm_retry_records_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("JAWM_")}
        self.env.update(PYTHONPATH=str(REPO), PYTHONDONTWRITEBYTECODE="1",
                        JAWM_CONFIG_FILE="/dev/null",
                        JAWM_MONITORING_DIRECTORY=str(self.root / "monitoring"))

    def run_workflow(self, source, expected):
        (self.root / "workflow.py").write_text(source)
        self.result = subprocess.run(
            [sys.executable, "-m", "jawm.cli", "workflow.py"],
            cwd=self.root, env=self.env, capture_output=True,
            text=True, timeout=60,
        )
        self.assertEqual(
            self.result.returncode, expected,
            self.result.stdout + self.result.stderr,
        )
        self.log = next((self.root / "logs").glob("step_*"))
        attempts_path = self.log / "attempts"
        return sorted(attempts_path.glob("attempt-*")) if attempts_path.exists() else []

    def test_success_without_retries_creates_no_attempt_directory(self):
        attempts = self.run_workflow(r"""
from jawm import Process
p = Process(name='step', retries=0, script='#!/bin/bash\necho success\n')
p.execute()
""", 0)
        self.assertEqual(attempts, [])
        self.assertFalse((self.log / "attempts").exists())
        self.assertEqual((self.log / "step.output").read_text(), "success\n")

    def test_failure_without_retries_creates_no_attempt_directory(self):
        attempts = self.run_workflow(r"""
from jawm import Process
p = Process(name='step', retries=0,
            script='#!/bin/bash\necho failed\necho problem >&2\nexit 7\n')
p.execute()
""", 1)
        self.assertEqual(attempts, [])
        self.assertFalse((self.log / "attempts").exists())
        self.assertEqual((self.log / "step.output").read_text(), "failed\n")
        self.assertEqual((self.log / "step.error").read_text(), "problem\n")
        self.assertEqual((self.log / "step.exitcode").read_text(), "7")

    def test_failed_attempt_is_copied_before_successful_retry(self):
        attempts = self.run_workflow(r"""
from jawm import Process
p = Process(name='step', retries=1,
    script='#!/bin/bash\nif [ ! -f tried ]; then touch tried; echo FIRST; echo FIRST_ERROR >&2; exit 7; fi\necho SECOND\necho SECOND_ERROR >&2\n')
p.execute()
""", 0)
        self.assertEqual([attempt.name for attempt in attempts], ["attempt-001"])
        first = attempts[0]
        self.assertEqual((first / "step.output").read_text(), "FIRST\n")
        self.assertEqual((first / "step.error").read_text(), "FIRST_ERROR\n")
        self.assertEqual((first / "step.exitcode").read_text(), "7")
        self.assertTrue((first / "step.script").exists())
        self.assertTrue((first / "step.command").exists())
        self.assertTrue((first / "step.id").read_text().isdigit())
        self.assertEqual((self.log / "step.output").read_text(), "SECOND\n")
        self.assertEqual((self.log / "step.error").read_text(), "SECOND_ERROR\n")
        self.assertEqual((self.log / "step.exitcode").read_text(), "0")

    def test_final_exhausted_attempt_remains_only_in_top_level_files(self):
        attempts = self.run_workflow(r"""
from jawm import Process
p = Process(name='step', retries=2,
    script='#!/bin/bash\nif [ ! -f tried_once ]; then touch tried_once; echo FIRST; exit 7; fi\nif [ ! -f tried_twice ]; then touch tried_twice; echo SECOND; exit 8; fi\necho FINAL\nexit 9\n')
p.execute()
""", 1)
        self.assertEqual(
            [attempt.name for attempt in attempts],
            ["attempt-001", "attempt-002"],
        )
        self.assertEqual((attempts[0] / "step.output").read_text(), "FIRST\n")
        self.assertEqual((attempts[0] / "step.exitcode").read_text(), "7")
        self.assertEqual((attempts[1] / "step.output").read_text(), "SECOND\n")
        self.assertEqual((attempts[1] / "step.exitcode").read_text(), "8")
        self.assertEqual((self.log / "step.output").read_text(), "FINAL\n")
        self.assertEqual((self.log / "step.exitcode").read_text(), "9")

    def test_copy_failure_is_warning_only_and_retry_still_succeeds(self):
        attempts = self.run_workflow(r"""
from jawm import Process
import jawm._process_internal as internal
def fail_copy(*args, **kwargs):
    raise OSError('synthetic copy failure')
internal.shutil.copy2 = fail_copy
p = Process(name='step', retries=1,
    script='#!/bin/bash\nif [ ! -f tried ]; then touch tried; echo FIRST; exit 7; fi\necho SECOND\n')
p.execute()
""", 0)
        self.assertEqual([attempt.name for attempt in attempts], ["attempt-001"])
        self.assertEqual(list(attempts[0].iterdir()), [])
        self.assertEqual((self.log / "step.output").read_text(), "SECOND\n")
        self.assertIn("Could not copy all retry records", self.result.stdout + self.result.stderr)

    def test_existing_attempt_directory_is_not_overwritten(self):
        attempts = self.run_workflow(r"""
from pathlib import Path
from jawm import Process
p = Process(name='step', retries=1,
    script='#!/bin/bash\nif [ ! -f tried ]; then touch tried; echo FIRST; exit 7; fi\necho SECOND\n')
archive = Path(p.log_path) / 'attempts' / 'attempt-001'
archive.mkdir(parents=True)
(archive / 'sentinel').write_text('keep')
p.execute()
""", 0)
        self.assertEqual([attempt.name for attempt in attempts], ["attempt-001"])
        self.assertEqual((attempts[0] / "sentinel").read_text(), "keep")
        self.assertFalse((attempts[0] / "step.output").exists())
        self.assertEqual((self.log / "step.output").read_text(), "SECOND\n")
        self.assertIn("Could not create retry records", self.result.stdout + self.result.stderr)

    def test_slurm_submission_failure_is_copied_before_retry(self):
        attempts = self.run_workflow(r"""
from types import SimpleNamespace
import jawm._process_slurm as backend
from jawm import Process
backend.subprocess.run = lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='submission rejected')
p = Process(name='step', manager='slurm', retries=1,
            script='#!/bin/bash\necho hello\n')
p.execute()
""", 1)
        self.assertEqual([attempt.name for attempt in attempts], ["attempt-001"])
        first = attempts[0]
        self.assertEqual((first / "step.exitcode").read_text(), "127")
        self.assertTrue((first / "step.slurm").exists())
        self.assertTrue((first / "step.script").exists())
        self.assertTrue((first / "step.command").exists())
        self.assertFalse((first / "step.sbatch_submit.log").exists())

    def test_kubernetes_submission_failure_is_copied_before_retry(self):
        attempts = self.run_workflow(r"""
from pathlib import Path
from types import SimpleNamespace
import jawm._process_kubernetes as backend
from jawm import Process
backend.subprocess.run = lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='apply rejected')
def manifest(self, attempt_i=None):
    self._generate_base_script()
    path = Path(self.log_path) / (self.name + '.k8s.json')
    path.write_text('{"attempt": %d}' % attempt_i)
    return str(path)
Process._generate_k8s_manifest = manifest
p = Process(name='step', manager='kubernetes', retries=1,
            script='#!/bin/bash\necho hello\n')
p.execute()
""", 1)
        self.assertEqual([attempt.name for attempt in attempts], ["attempt-001"])
        first = attempts[0]
        self.assertEqual((first / "step.k8s.json").read_text(), '{"attempt": 1}')
        self.assertIn("apply rejected", (first / "step.kubectl_apply.log").read_text())
        self.assertTrue((first / "step.script").exists())
        self.assertTrue((first / "step.command").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
