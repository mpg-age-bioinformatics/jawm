"""Retry evidence regression tests: python test/retry_records_test.py."""
import hashlib
import json
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
        result = subprocess.run([sys.executable, "-m", "jawm.cli", "workflow.py"],
                                cwd=self.root, env=self.env, capture_output=True,
                                text=True, timeout=60)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.log = next((self.root / "logs").glob("step_*"))
        attempts = sorted((self.log / "attempts").glob("attempt-*"))
        for attempt in attempts:
            start = json.loads((attempt / "started.json").read_text())
            end = json.loads((attempt / "completed.json").read_text())
            self.assertLessEqual(start["started_at"], end["ended_at"])
            for name, digest in end["records_sha256"].items():
                self.assertEqual(hashlib.sha256((attempt / name).read_bytes()).hexdigest(), digest)
        return attempts

    def test_failed_then_successful_retry_preserves_both_attempts(self):
        attempts = self.run_workflow(r"""
from jawm import Process
p = Process(name='step', retries=1,
    script='#!/bin/bash\nif [ ! -f tried ]; then touch tried; echo FIRST_ATTEMPT; echo FIRST_ERROR >&2; exit 7; fi\necho SECOND_ATTEMPT\necho SECOND_ERROR >&2\n',
    retry_overrides={1: {'manager_local': {'memory': '2G'}}})
p.execute()
""", 0)
        self.assertEqual(len(attempts), 2)
        for i, (label, code) in enumerate([("FIRST", "7"), ("SECOND", "0")]):
            attempt = attempts[i]
            self.assertEqual((attempt / "step.output").read_text(), label + "_ATTEMPT\n")
            self.assertEqual((attempt / "step.error").read_text(), label + "_ERROR\n")
            self.assertEqual((attempt / "step.exitcode").read_text(), code)
            self.assertIn(label, (attempt / "step.script").read_text())
            self.assertTrue((attempt / "step.command").read_text())
            self.assertTrue((attempt / "step.id").read_text().isdigit())
        config = json.loads((attempts[1] / "started.json").read_text())["effective_configuration"]
        self.assertEqual(config["manager_local"]["memory"], "2G")
        self.assertEqual((self.log / "step.output").read_text(), "SECOND_ATTEMPT\n")
        # Archives are independent copies, not aliases to the current files.
        (self.log / "step.output").write_text("replaced")
        self.assertEqual((attempts[1] / "step.output").read_text(), "SECOND_ATTEMPT\n")

    def test_exhausted_retries_preserve_every_exit(self):
        attempts = self.run_workflow(r"""
from jawm import Process
p = Process(name='step', retries=1, script='#!/bin/bash\necho failed\nexit 7\n')
p.execute()
""", 1)
        self.assertEqual(len(attempts), 2)
        self.assertEqual([(a / "step.exitcode").read_text() for a in attempts], ["7", "7"])

    def test_launch_failure_does_not_inherit_previous_pid_or_stdout(self):
        attempts = self.run_workflow(r"""
from jawm import Process
import jawm._process_local as backend
original_popen = backend.subprocess.Popen
calls = 0
def launch(*args, **kwargs):
    global calls
    calls += 1
    if calls == 2:
        raise OSError('synthetic launch failure')
    return original_popen(*args, **kwargs)
backend.subprocess.Popen = launch
p = Process(name='step', retries=1, script='#!/bin/bash\necho FIRST\nexit 7\n')
p.execute()
""", 1)
        self.assertEqual(len(attempts), 2)
        self.assertFalse((attempts[1] / "step.id").exists())
        self.assertEqual((attempts[1] / "step.output").read_text(), "")
        self.assertEqual((attempts[1] / "step.exitcode").read_text(), "127")
        self.assertIn("FIRST", (attempts[0] / "step.output").read_text())

    def test_archive_failure_stops_retry_and_fails_cli(self):
        self.assert_archive_failure(7)

    def test_archive_failure_after_success_still_fails_cli(self):
        self.assert_archive_failure(0)

    def assert_archive_failure(self, child_exit):
        # Fail the first archive copy, after the child has written its evidence.
        result_source = r"""
import builtins
from jawm import Process
original_open = builtins.open
def fail_archive(path, mode='r', *args, **kwargs):
    if '/attempts/attempt-' in str(path) and str(path).endswith('.output') and mode == 'xb':
        raise OSError('synthetic archive failure')
    return original_open(path, mode, *args, **kwargs)
builtins.open = fail_archive
p = Process(name='step', retries=1, script='#!/bin/bash\nif [ -f tried ]; then touch SHOULD_NOT_RUN; fi\ntouch tried\necho ORIGINAL\nexit 7\n')
p.execute()
"""
        (self.root / "workflow.py").write_text(result_source.replace("exit 7", "exit " + str(child_exit)))
        r = subprocess.run([sys.executable, "-m", "jawm.cli", "workflow.py"],
                           cwd=self.root, env=self.env, capture_output=True, text=True, timeout=45)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertFalse((self.root / "SHOULD_NOT_RUN").exists())
        log = next((self.root / "logs").glob("step_*"))
        self.assertEqual((log / "step.output").read_text(), "ORIGINAL\n")
        attempt = next((log / "attempts").glob("attempt-*"))
        self.assertTrue((attempt / "started.json").exists())
        self.assertFalse((attempt / "completed.json").exists())

    def test_slurm_submission_failures_preserve_scripts_and_full_response(self):
        attempts = self.run_workflow(r"""
from types import SimpleNamespace
import jawm._process_slurm as backend
from jawm import Process
backend.subprocess.run = lambda *a, **k: SimpleNamespace(returncode=1, stdout='', stderr='submission rejected')
p = Process(name='step', manager='slurm', retries=1, script='#!/bin/bash\necho hello\n')
p.execute()
""", 1)
        self.assertEqual(len(attempts), 2)
        for attempt in attempts:
            self.assertEqual((attempt / "step.exitcode").read_text(), "127")
            self.assertIn("submission rejected", (attempt / "step.sbatch_submit.log").read_text())
            self.assertTrue((attempt / "step.slurm").exists())
            self.assertTrue((attempt / "step.script").exists())

    def test_kubernetes_submission_failures_preserve_manifests_and_response(self):
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
p = Process(name='step', manager='kubernetes', retries=1, script='#!/bin/bash\necho hello\n')
p.execute()
""", 1)
        self.assertEqual(len(attempts), 2)
        for i, attempt in enumerate(attempts, 1):
            self.assertEqual(json.loads((attempt / "step.k8s.json").read_text())["attempt"], i)
            self.assertIn("apply rejected", (attempt / "step.kubectl_apply.log").read_text())
            self.assertEqual((attempt / "step.exitcode").read_text(), "127")

    def test_repeated_attempt_numbers_cannot_replace_previous_archives(self):
        attempts = self.run_workflow(r"""
from pathlib import Path
from jawm import Process
p = Process(name='step', script='#!/bin/bash\necho unused\n')
Path(p.log_path).mkdir(parents=True)
def attempt(number, total):
    (Path(p.log_path) / 'step.output').write_text(str(number))
    return 0
p._run_recorded_attempt(attempt, 1, 1)
first = next((Path(p.log_path) / 'attempts').glob('attempt-*'))
original = {f.name: f.read_bytes() for f in first.iterdir()}
p._run_recorded_attempt(attempt, 1, 1)
assert original == {f.name: f.read_bytes() for f in first.iterdir()}
""", 0)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len(list((self.log / "attempts").glob("previous-*"))), 1)

    def test_unexpected_exception_preserves_partial_records(self):
        attempts = self.run_workflow(r"""
from pathlib import Path
from jawm import Process
p = Process(name='step', script='#!/bin/bash\necho unused\n')
Path(p.log_path).mkdir(parents=True)
def attempt(number, total):
    (Path(p.log_path) / 'step.output').write_text('partial stdout')
    (Path(p.log_path) / 'step.error').write_text('partial stderr')
    raise RuntimeError('synthetic monitoring error')
try:
    p._run_recorded_attempt(attempt, 1, 1)
except RuntimeError as exc:
    p._proc_exception_handler(exc)
""", 1)
        self.assertEqual(len(attempts), 1)
        self.assertEqual((attempts[0] / "step.error").read_text(), "partial stderr")
        self.assertIn("partial stderr", (self.log / "step.error").read_text())
        self.assertEqual(json.loads((attempts[0] / "completed.json").read_text())["exception"],
                         "synthetic monitoring error")

    def test_slurm_completed_attempts_preserve_raw_exit_codes_and_streams(self):
        attempts = self.run_workflow(r"""
from pathlib import Path
from types import SimpleNamespace
from jawm import Process
import jawm._process_slurm as backend
job = 0
def scheduler(command, **kwargs):
    global job
    if command[0] == 'sbatch':
        job += 1
        Path(command[command.index('--output') + 1]).write_text('output ' + str(job))
        Path(command[command.index('--error') + 1]).write_text('error ' + str(job))
        return SimpleNamespace(returncode=0, stdout=str(job), stderr='')
    if command[0] == 'sacct':
        state = 'FAILED 7:0' if job == 1 else 'COMPLETED 0:0'
        return SimpleNamespace(returncode=0, stdout=str(job) + ' ' + state, stderr='')
    raise AssertionError(command)
backend.subprocess.run = scheduler
Process._finish_wait_and_settle = lambda *a, **k: None
p = Process(name='step', manager='slurm', retries=1, script='#!/bin/bash\necho hello\n')
p.execute()
""", 0)
        self.assertEqual(len(attempts), 2)
        for i, raw_code in enumerate(["7:0", "0:0"]):
            self.assertEqual((attempts[i] / "step.exitcode").read_text(), raw_code)
            self.assertEqual((attempts[i] / "step.output").read_text(), "output " + str(i + 1))
            self.assertEqual((attempts[i] / "step.error").read_text(), "error " + str(i + 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
