"""Non-production audit probes for JAWM; creates only a temporary working area.

Usage: python3 jawm_gxp_probes.py /absolute/path/to/jawm
The JSON observations are evidence of behavior, not a validation certificate.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

repo = Path(sys.argv[1]).resolve()
root = Path(tempfile.mkdtemp(prefix="jawm_gxp_review_"))
env = {
    "PATH": os.environ["PATH"],
    "PYTHONPATH": str(repo),
    "PYTHONDONTWRITEBYTECODE": "1",
    "JAWM_CONFIG_FILE": "/dev/null",
    "JAWM_MONITORING_DIRECTORY": str(root / "monitoring"),
    "JAWM_URL_CACHE_DIR": str(root / "url_cache"),
    "JAWM_LOG_EMOJI": "0",
}
os.environ["JAWM_CONFIG_FILE"] = "/dev/null"
sys.path.insert(0, str(repo))
from jawm._utils import hash_content

observations = {"repository": str(repo), "work_area": str(root), "python": sys.version, "cases": {}}

def run(label, cwd, args, command=None):
    result = subprocess.run(command or [sys.executable, "-m", "jawm.cli", *args],
                            cwd=cwd, env=env, text=True, capture_output=True, timeout=90)
    log = (result.stdout or "") + (result.stderr or "")
    (root / (label + ".log")).write_text(log)
    return result.returncode, log

def case(name):
    path = root / name
    path.mkdir()
    return path

d = case("aggregate_hash")
(d / "a.txt").write_text("AB")
(d / "b.txt").write_text("C")
before = hash_content(str(d))
(d / "a.txt").write_text("A")
(d / "b.txt").write_text("BC")
after = hash_content(str(d))
observations["cases"]["aggregate_hash"] = {"two_files_changed_but_digest_equal": before == after,
    "digest": after, "note": "AB+C versus A+BC; no SHA-256 collision needed"}

d = case("hash_exit")
(d / "workflow.py").write_text("print('synthetic workflow')\n")
(d / "out.txt").write_text("baseline")
(d / "params.yaml").write_text("- scope: hash\n  include: [out.txt]\n  overwrite: false\n")
rc1, _ = run("hash_baseline", d, ["workflow.py", "-p", "params.yaml"])
(d / "out.txt").write_text("changed")
rc2, log2 = run("hash_changed", d, ["workflow.py", "-p", "params.yaml"])
(d / "reference.yaml").write_text("- scope: hash\n  include: [out.txt]\n  reference: " + hashlib.sha256(b"baseline").hexdigest() + "\n")
rc3, log3 = run("hash_reference", d, ["workflow.py", "-p", "reference.yaml"])
(d / "workflow.py").write_text("import sys\nsys.exit(0)\n")
rc4, log4 = run("hash_reference_exit_zero", d, ["workflow.py", "-p", "reference.yaml"])
observations["cases"]["hash_exit"] = {"baseline_rc": rc1, "changed_without_reference_rc": rc2,
    "mismatch_reported": "STATUS: MISMATCHED" in log2, "explicit_reference_mismatch_rc": rc3,
    "explicit_reference_mismatch_after_workflow_sys_exit_zero_rc": rc4,
    "reference_failure_logged_after_sys_exit_zero": "does NOT match reference" in log4}

d = case("resume")
(d / "input.txt").write_text("original")
(d / "workflow.py").write_text("from jawm import Process\np = Process(name='copy_input', script='#!/bin/bash\\ncat input.txt > output.txt\\n', resume=True)\np.execute()\nProcess.wait(p.hash)\n")
rc1, _ = run("resume_original", d, ["workflow.py"])
(d / "input.txt").write_text("changed")
rc2, log2 = run("resume_changed", d, ["workflow.py"])
retained = (d / "output.txt").read_text()
(d / "output.txt").unlink()
rc3, log3 = run("resume_deleted_output", d, ["workflow.py"])
observations["cases"]["resume"] = {"original_rc": rc1, "changed_input_rc": rc2,
    "changed_input_skipped": "skipped with resume enabled" in log2, "output_after_input_change": retained,
    "deleted_output_rc": rc3, "deleted_output_skipped": "skipped with resume enabled" in log3,
    "output_restored": (d / "output.txt").exists()}

d = case("child_failure")
(d / "workflow.py").write_text("from jawm import Process\np = Process(name='fail_step', script='#!/bin/bash\\nexit 7\\n')\np.execute()\n")
rc, log = run("child_failure", d, ["workflow.py"])
exit_files = list((d / "logs").glob("*/fail_step.exitcode"))
observations["cases"]["child_failure"] = {"workflow_cli_rc": rc,
    "child_exitcode": exit_files[0].read_text() if exit_files else None}

d = case("retry_records")
(d / "workflow.py").write_text("from jawm import Process\np = Process(name='retry_step', retries=1, script='#!/bin/bash\\nif [ ! -f tried ]; then echo FIRST_ATTEMPT; touch tried; exit 1; fi\\necho SECOND_ATTEMPT\\n')\np.execute()\nProcess.wait(p.hash)\n")
rc, _ = run("retry_records", d, ["workflow.py"])
outputs = list((d / "logs").glob("*/retry_step.output"))
observations["cases"]["retry_records"] = {"workflow_cli_rc": rc,
    "retained_stdout": outputs[0].read_text() if outputs else None, "stdout_file_count": len(outputs)}

d = case("jawm_test_stale_hash")
(d / "test").mkdir()
(d / "workflow.py").write_text("print('synthetic regression workflow')\n")
(d / "out.txt").write_text("baseline")
(d / "params.yaml").write_text("- scope: hash\n  include: [out.txt]\n  overwrite: false\n")
expected = hashlib.sha256(b"baseline").hexdigest()
(d / "test" / "tests.txt").write_text('# module;workflow;params;name;hash\nworkflow.py;main;params.yaml;"synthetic";' + expected + '\n')
cmd = ["/bin/bash", "-e", str(repo / "jawm/data/jawm-test"), "--module_versions", "current", "--jawm_repo", str(repo)]
rc1, _ = run("jawm_test_baseline", d, [], command=cmd)
(d / "out.txt").write_text("changed")
rc2, log2 = run("jawm_test_changed", d, [], command=cmd)
observations["cases"]["jawm_test_stale_hash"] = {"baseline_rc": rc1,
    "changed_output_rc": rc2, "cli_mismatch_reported": "STATUS: MISMATCHED" in log2,
    "test_runner_reads_old_hash": "Generated HASH: " + expected in log2}

(root / "observations.json").write_text(json.dumps(observations, indent=2) + "\n")
print(json.dumps(observations, indent=2))
