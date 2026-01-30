import os
import time
import sys
import subprocess
import shutil
import tempfile
import re
import json
import copy
from glob import glob
from jawm import Process, utils

passed = 0
failed = 0

Process.reset_stop()

# Create a base temp folder in current location
base_tmp = os.path.join(os.getcwd(), "logs_temp")
os.makedirs(base_tmp, exist_ok=True)

# Create a snapshot of the Process default/override values
bak_default = copy.deepcopy(Process.default_parameters)
bak_override = copy.deepcopy(Process.override_parameters)

def _clear_params():
    Process.default_parameters.clear()
    Process.override_parameters.clear()

def _restore_params(snap_default, snap_override):
    Process.default_parameters.clear()
    Process.default_parameters.update(snap_default)
    Process.override_parameters.clear()
    Process.override_parameters.update(snap_override)


# ------------------------------------------------------------
#  Start of test cases
# ------------------------------------------------------------

print(">>> Test 1: Basic Inline Script Execution")
# time.sleep(0.5)
try:
    proc1 = Process(
        name="basic_hello",
        script="""#!/usr/bin/env python3
print('Hello jawm!')
""",
        logs_directory="logs_test"
    )
    proc1.execute()
    Process.wait(proc1.hash)
    assert proc1.get_exitcode().startswith("0"), "❌ Basic execution failed"
    print("✅ Passed: Basic Inline Script")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 2: Dependency Handling")
# time.sleep(0.5)
try:
    proc2a = Process(
        name="step_a",
        script="""#!/bin/bash
echo 'Step A done'
""",
        logs_directory="logs_test"
    )
    proc2b = Process(
        name="step_b",
        script="""#!/usr/bin/env python3
print('Step B done')
""",
        depends_on=["step_a"],
        logs_directory="logs_test"
    )
    proc2a.execute()
    proc2b.execute()
    Process.wait(["step_a", "step_b"])
    assert proc2a.get_exitcode().startswith("0"), "❌ step_a failed"
    assert proc2b.get_exitcode().startswith("0"), "❌ step_b failed"
    print("✅ Passed: Dependency Handling")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 3: Retry Mechanism")
# time.sleep(0.5)
try:
    proc3 = Process(
        name="retry_test",
        script="""#!/bin/bash
fakecommandddddd
""",
        retries=1,
        logs_directory="logs_test"
    )
    try:
        proc3.execute()
        Process.wait(proc3.hash)
    except RuntimeError:
        pass
    assert not proc3.get_exitcode().startswith("0"), "❌ Retry test unexpectedly succeeded"
    time.sleep(0.2)
    print("✅ Passed: Retry Mechanism")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1

# Clear any global state
Process.reset_stop()


print("\n>>> Test 4: Output, Error, and Command Log Check")
# time.sleep(0.5)
try:
    output = proc2b.get_output()
    error = proc2b.get_error()
    command = proc2b.get_command()
    assert output is not None, "❌ Output log missing"
    assert error is not None, "❌ Error log missing"
    assert command is not None, "❌ Command log missing"
    print("✅ Passed: Log Retrieval Checks")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 5: Process Registry Summary")
# time.sleep(0.5)
try:
    all_procs = Process.list_all()
    assert all(p["finished"] for p in all_procs), "❌ Some processes not marked finished"
    print(f"✅ Passed: {len(all_procs)} Process(es) tracked and marked finished")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 6: Script Variable Substitution")
# time.sleep(0.5)
try:
    proc6 = Process(
        name="var_subst",
        script="""#!/usr/bin/env python3
print("Job name is {{APPNAME}}")
""",
        var={"APPNAME": "jawm-Test"},
        logs_directory="logs_test"
    )
    proc6.execute()
    Process.wait(proc6.hash)
    out6 = proc6.get_output()
    assert "jawm-Test" in out6, "❌ var not substituted correctly"
    print("✅ Passed: Script Variable Substitution")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 7: Script Variable File Substitution")
# time.sleep(0.5)

try:
    os.makedirs("data_test", exist_ok=True)
    
    # Create a simple .rc file
    with open("data_test/vars.rc", "w") as f:
        f.write("GREETING=Hello from file\n")
    
    proc7 = Process(
        name="file_vars",
        script="""#!/bin/bash
echo "{{GREETING}}"
""",
        var_file="data_test/vars.rc",
        logs_directory="logs_test"
    )
    proc7.execute()
    Process.wait(proc7.hash)
    out7 = proc7.get_output()
    assert "Hello from file" in out7, "❌ var_file substitution failed"
    print("✅ Passed: Script Variable File Substitution")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 8: Skipped Process using `when=False`")
# time.sleep(0.5)
try:
    proc8 = Process(
        name="skip_this",
        script="""#!/bin/bash
echo 'Should not run' > skip.txt
""",
        when=False,
        logs_directory="logs_test"
    )
    proc8.execute()
    assert proc8.finished_event.is_set(), "❌ Skipped process did not mark finished"
    assert not os.path.exists(os.path.join(proc8.log_path, "skip.txt")), "❌ Script ran despite when=False"
    print("✅ Passed: Conditional Skip with `when=False`")
    passed += 1
except Exception as e:
    print(f"❌ {e}")
    failed += 1

Process.reset_stop()


print("\n>>> Test 9: Process Cloning with `clone()`")
# time.sleep(0.5)
try:
    original = Process(
        name="original_proc",
        script="""#!/bin/bash
echo 'Original'
""",
        logs_directory="logs_test"
    )
    clone = original.clone(name="cloned_proc", script="""#!/bin/bash
echo 'Cloned'
""")
    original.execute()
    clone.execute()
    Process.wait(["original_proc", "cloned_proc"])
    assert "original_proc" in Process.registry
    assert "cloned_proc" in Process.registry
    print("✅ Passed: Process Copy and Execution")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 10: Class-Level Defaults with `set_default()`")
# time.sleep(0.5)
try:
    Process.set_default(retries=3, logs_directory="logs_test_default")

    proc10 = Process(
        name="default_param_proc",
        script="""#!/bin/bash
echo 'Check default retries'
"""
    )
    assert proc10.params.get("retries") == 3, "❌ Default parameter (retries) not applied"
    assert "logs_test_default" in proc10.logs_directory, "❌ logs_directory default not applied"
    print("✅ Passed: Class-Level Default Parameters")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

Process.default_parameters.clear()


print("\n>>> Test 11: Parameter Resolution from YAML (Global and Process)")
# time.sleep(0.5)
try:
    with open("data_test/test_params.yaml", "w") as f:
        f.write("""
- scope: global
  retries: 1
  logs_directory: "logs_from_yaml_global"

- scope: process
  name: "yaml_specific_proc"
  retries: 5
  logs_directory: "logs_from_yaml_process"
""")

    proc11 = Process(
        name="yaml_specific_proc",
        script="""#!/bin/bash
echo 'YAML parameter test'
""",
        param_file="data_test/test_params.yaml"
    )

    if proc11.manager=="local" and proc11.environment=="local":
        assert proc11.retries == 5, "❌ Process-specific value not applied"
        assert "logs_from_yaml_process" in proc11.logs_directory, "❌ logs_directory not from process scope"
    print("✅ Passed: YAML Parameter Resolution (skipped for cli override)")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 12: Validation Logic (Basic vs. Strict)")
# time.sleep(0.5)
try:
    # Valid process with minor warning (unknown key) → should pass in basic mode
    proc12a = Process(
        name="valid_proc_basic",
        script="""#!/bin/bash\necho 'Basic test'""",
        unknown_param="foo",  # not defined
        validation=True
    )
    assert proc12a.is_valid("basic"), "❌ Basic validation failed when it should have passed"

    # Valid process with same unknown param → should still pass in strict mode (logs warning only)
    proc12b = Process(
        name="valid_proc_strict",
        script="""#!/bin/bash\necho 'Strict test'""",
        unknown_param="foo",
        validation="strict"
    )
    assert not proc12b.is_valid("strict"), "❌ Strict validation incorrectly failed on warning-only input"

    # Invalid process (missing shebang) → should fail in both modes
    proc12c = Process(
        name="invalid_proc_strict",
        script="""echo 'Missing shebang!'""",
        validation="strict"
    )
    assert not proc12c.is_valid("strict"), "❌ Strict validation passed despite missing shebang"
    assert not proc12c.is_valid("basic"), "❌ Basic validation passed despite missing shebang"


    # Callable test → `when` as function is allowed
    proc12d = Process(
        name="proc_callable_when",
        script="#!/bin/bash\necho 'Callable test'",
        when=lambda: True
    )
    assert proc12d.is_valid("strict"), "❌ Callable 'when' incorrectly failed validation"

    # Callable where not allowed (e.g., retries) → should trigger a warning in strict
    proc12e = Process(
        name="proc_callable_retries",
        script="#!/bin/bash\necho 'Invalid callable'",
        retries=lambda: 3,
        validation="strict"
    )
    assert not proc12e.is_valid("strict"), "❌ Callable retries should not be allowed in strict mode"

    # Placeholder validation: missing {{PLACEHOLDER}} → should warn/fail in strict
    proc12f = Process(
        name="proc_placeholder_missing",
        script="""#!/bin/bash\necho "{{UNDEFINED_VAR}}"\n""",
        validation="strict"
    )
    assert not proc12f.is_valid("strict"), "❌ Strict validation passed despite missing placeholder variable"
    assert proc12f.is_valid("basic"), "❌ Basic validation failed on missing placeholder (should allow)"

    # Placeholder defined → should pass
    proc12g = Process(
        name="proc_placeholder_ok",
        script="""#!/bin/bash\necho "{{MESSAGE}}"\n""",
        var={"MESSAGE": "Hello"},
        validation="strict"
    )
    assert proc12g.is_valid("strict"), "❌ Placeholder defined but still failed strict validation"


    print("✅ Passed: Validation Logic (Basic & Strict Modes)")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

Process.reset_stop()


print("\n>>> Test 13: jawm CLI Integration ")
# time.sleep(0.5)

try:
    # Pick how to invoke the CLI: prefer console script, else module
    def cli_cmd(args):
        if shutil.which("jawm"):
            return ["jawm", *args]
        # Fallback to python -m jawm.cli (works without pip-installing console_script)
        return [sys.executable, "-m", "jawm.cli", *args]

    def run_cli(args, timeout=60):
        r = subprocess.run(cli_cmd(args), capture_output=True, text=True, timeout=timeout)
        both = (r.stdout or "") + (r.stderr or "")
        return r.returncode, r.stdout, r.stderr, both

    # Use a temporary working directory to avoid collisions on CI
    with tempfile.TemporaryDirectory(prefix="cli_it_", dir=base_tmp) as root:

        # -------------------------
        # A) -v: variables from YAML FILE
        # -------------------------
        a_dir = os.path.join(root, "vars_yaml_file")
        os.makedirs(a_dir, exist_ok=True)
        with open(os.path.join(a_dir, "main.py"), "w") as f:
            f.write("print('GREETING=', GREETING); print('X=', X)\n")
        with open(os.path.join(a_dir, "vars.yaml"), "w") as f:
            f.write("GREETING: 'HiFromYAML'\nX: 42\n")
        rc, out, err, both = run_cli([a_dir, "-v", os.path.join(a_dir, "vars.yaml")])
        assert rc == 0, "❌ CLI failed for -v YAML file"
        assert "GREETING= HiFromYAML" in both and "X= 42" in both, "❌ YAML variables not injected"

        # -------------------------
        # B) -v: variables from YAML DIRECTORY (merges multiple files)
        # -------------------------
        b_dir = os.path.join(root, "vars_yaml_dir")
        os.makedirs(b_dir, exist_ok=True)
        with open(os.path.join(b_dir, "main.py"), "w") as f:
            f.write("print('A=', A); print('B=', B)\n")
        with open(os.path.join(b_dir, "one.yaml"), "w") as f:
            f.write("A: 'from_dir_1'\n")
        with open(os.path.join(b_dir, "two.yml"), "w") as f:
            f.write("B: 'from_dir_2'\n")
        rc, out, err, both = run_cli([b_dir, "-v", b_dir])
        assert rc == 0, "❌ CLI failed for -v YAML directory"
        assert "A= from_dir_1" in both and "B= from_dir_2" in both, "❌ YAML directory variables not injected"

        # -------------------------
        # C) -v: variables from .rc FILE
        # -------------------------
        c_dir = os.path.join(root, "vars_rc")
        os.makedirs(c_dir, exist_ok=True)
        with open(os.path.join(c_dir, "main.py"), "w") as f:
            f.write("print('HELLO=', HELLO); print('NUM=', NUM)\n")
        with open(os.path.join(c_dir, "vars.rc"), "w") as f:
            f.write('HELLO="rc_hello"\nNUM=7\n')
        rc, out, err, both = run_cli([c_dir, "-v", os.path.join(c_dir, "vars.rc")])
        assert rc == 0, "❌ CLI failed for -v .rc file"
        assert "HELLO= rc_hello" in both and "NUM= 7" in both, "❌ .rc variables not injected"

        # -------------------------
        # D) -p: parameter file affects Process config (e.g., logs_directory)
        # -------------------------
        d_dir = os.path.join(root, "params_file")
        os.makedirs(d_dir, exist_ok=True)
        with open(os.path.join(d_dir, "main.py"), "w") as f:
            f.write(
                "from jawm import Process\n"
                "p = Process(name='cli_p_test', script='#!/bin/bash\\necho hi')\n"
                "print('PROC_LOG_DIR=', p.logs_directory)\n"
            )
        with open(os.path.join(d_dir, "params.yaml"), "w") as f:
            f.write(
                "- scope: global\n"
                "  logs_directory: test_logs_from_params_cli\n"
            )
        rc, out, err, both = run_cli([d_dir, "-p", os.path.join(d_dir, "params.yaml")])
        assert rc == 0, "❌ CLI failed for -p"
        assert "PROC_LOG_DIR=" in both and "test_logs_from_params_cli" in both, "❌ -p did not influence Process.logs_directory"

        # -------------------------
        # E) --logs_directory: creates CLI run log under <dir>/jawm_runs/
        # -------------------------
        e_dir = os.path.join(root, "logs_dir_check")
        os.makedirs(e_dir, exist_ok=True)
        with open(os.path.join(e_dir, "main.py"), "w") as f:
            f.write("print('JUST_RUN')\n")
        custom_logs = os.path.join(root, "custom_cli_logs")
        rc, out, err, both = run_cli([e_dir, "-l", custom_logs])
        assert rc == 0, "❌ CLI failed with --logs_directory"
        runs_dir = os.path.join(custom_logs, "jawm_runs")
        assert os.path.isdir(runs_dir), "❌ CLI did not create <logs_directory>/jawm_runs"
        log_files = glob(os.path.join(runs_dir, "*.log"))
        assert log_files, "❌ No CLI run log file created in logs directory"

        # -------------------------
        # F) -r / --resume: accepted and doesn’t crash (don’t assert on wording)
        # -------------------------
        f_dir = os.path.join(root, "resume_flag")
        os.makedirs(f_dir, exist_ok=True)
        with open(os.path.join(f_dir, "main.py"), "w") as f:
            f.write("print('RESUME_TEST_RUN')\n")
        rc, out, err, both = run_cli([f_dir, "-r"])
        assert rc == 0 and "RESUME_TEST_RUN" in both, "❌ CLI failed with -r"

        # Also accept no-override flag spelling & short form (-n)
        rc, out, err, both = run_cli([f_dir, "-r", "--no-override"])
        assert rc == 0, "❌ CLI failed with --no-override"
        rc, out, err, both = run_cli([f_dir, "-r", "-n", "resume"])
        assert rc == 0, "❌ CLI failed with -n resume"

        # -------------------------
        # G) Path resolution: jawm.py preferred over main.py
        # -------------------------
        g_dir = os.path.join(root, "prefer_jawm_py")
        os.makedirs(g_dir, exist_ok=True)
        with open(os.path.join(g_dir, "main.py"), "w") as f:
            f.write("print('RUN_MAIN')\n")
        with open(os.path.join(g_dir, "jawm.py"), "w") as f:
            f.write("print('RUN_jawm')\n")
        rc, out, err, both = run_cli([g_dir])
        assert rc == 0 and "RUN_jawm" in both and "RUN_MAIN" not in both, "❌ Did not prefer jawm.py over main.py"

        # -------------------------
        # H) Path resolution: directory with single .py (not main/jawm)
        # -------------------------
        h_dir = os.path.join(root, "single_py")
        os.makedirs(h_dir, exist_ok=True)
        with open(os.path.join(h_dir, "only.py"), "w") as f:
            f.write("print('RUN_ONLY')\n")
        rc, out, err, both = run_cli([h_dir])
        assert rc == 0 and "RUN_ONLY" in both, "❌ Did not execute single .py in directory"

        # -------------------------
        # I) Path resolution: multiple .py without main/jawm → should error
        # -------------------------
        i_dir = os.path.join(root, "multiple_py_error")
        os.makedirs(i_dir, exist_ok=True)
        with open(os.path.join(i_dir, "a.py"), "w") as f:
            f.write("print('A')\n")
        with open(os.path.join(i_dir, "b.py"), "w") as f:
            f.write("print('B')\n")
        rc, out, err, both = run_cli([i_dir])
        assert rc != 0, "❌ CLI should fail for directory with multiple .py and no main/jawm"

        # -------------------------
        # J) Direct .py path works
        # -------------------------
        j_dir = os.path.join(root, "direct_py")
        os.makedirs(j_dir, exist_ok=True)
        target_py = os.path.join(j_dir, "script.py")
        with open(target_py, "w") as f:
            f.write("print('RUN_DIRECT')\n")
        rc, out, err, both = run_cli([target_py])
        assert rc == 0 and "RUN_DIRECT" in both, "❌ Did not execute direct .py path"

        # -------------------------
        # K) Invalid path → clean error (don’t rely on exact wording)
        # -------------------------
        missing = os.path.join(root, "definitely_not_here_12345")
        rc, out, err, both = run_cli([missing])
        assert rc != 0, "❌ CLI should fail on invalid path"

    print("✅ Passed: CLI options & path resolution")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

Process.reset_stop()


print("\n>>> Test 14: Hash Prefix Consistency for Identical Parameters")
# time.sleep(0.5)
try:
    proc14a = Process(
        name="hash_test",
        script="#!/bin/bash\necho Hello",
        logs_directory="logs_test_hash"
    )

    proc14b = Process(
        name="hash_test",
        script="#!/bin/bash\necho Hello",
        logs_directory="logs_test_hash"
    )

    prefix_a = proc14a.hash[:6]
    prefix_b = proc14b.hash[:6]

    assert prefix_a == prefix_b, f"❌ Expected matching hash prefixes, got {prefix_a} and {prefix_b}"
    assert proc14a.hash != proc14b.hash, f"❌ Full hashes should differ due to random suffix: {proc14a.hash}"
    assert len(proc14a.hash) == 10 and len(proc14b.hash) == 10, "❌ Hash length should be 10 characters"

    print(f"✅ Passed: Hash prefix match → {prefix_a}")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 15: Resume Skips Execution if Previous Run Succeeded")
# time.sleep(0.5)
try:
    # Step 1: Run the original process
    proc15a = Process(
        name="resume_test_proc",
        script="""#!/bin/bash\necho 'Resumable process'""",
        logs_directory="logs_resume_test",
    )
    proc15a.execute()
    Process.wait(proc15a.hash)

    assert proc15a.get_exitcode().startswith("0"), "❌ First run did not finish successfully"

    # Step 2: Clone the process
    proc15b = proc15a.clone()
    proc15b.resume = True
    proc15b.execute()

    Process.wait(proc15b.hash)

    # Step 3: Confirm resume behavior
    assert proc15b.log_path == proc15a.log_path, "❌ Resume did not use existing log folder"
    assert proc15b.get_exitcode().startswith("0"), "❌ Resume did not resolve to a successful result"
    assert proc15b.finished_event.is_set(), "❌ Resume process did not mark itself as finished"
    assert proc15b.execution_end_at is not None, "❌ Resume process was not marked as completed"

    print(f"✅ Passed: Resume correctly skipped execution and reused logs from {os.path.basename(proc15b.log_path)}")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 16: Class-Level Overrides with `set_override()`")
# time.sleep(0.5)
try:
    # Clear any defaults/overrides first
    _clear_params()

    # Set a default first
    Process.set_default(retries=1, logs_directory="logs_default_override")

    # Now set an override that should win over defaults and instance args
    Process.set_override(retries=5, logs_directory="logs_override_test")

    # Even if we pass retries=2 in constructor, override should still win
    proc16 = Process(
        name="override_param_proc",
        script="""#!/usr/bin/env python3
    print('Check override retries')
    """,
        retries=2,
        logs_directory="logs_should_be_overridden"
    )

    assert proc16.params.get("retries") == 5, "❌ Override parameter (retries) not applied"
    assert "logs_override_test" in proc16.logs_directory, "❌ logs_directory override not applied"

    print("✅ Passed: Class-Level Override Parameters")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    # Cleanup overrides for other tests
    _restore_params(bak_default, bak_override)


print("\n>>> Test 17: update_vars() supports list of files and YAML directory")
# time.sleep(0.5)
try:

    # ---------- A) List of files ----------
    tmpA = tempfile.mkdtemp(prefix="update_vars_list_", dir=base_tmp)
    try:
        # Two YAML files: one global, one process-specific
        v1 = os.path.join(tmpA, "v1.yaml")
        v2 = os.path.join(tmpA, "v2.yml")

        with open(v1, "w") as f:
            f.write("""
- scope: global
  var:
    MSG: "from_v1_global"
    other: "X1"
""")

        with open(v2, "w") as f:
            f.write("""
- scope: process
  name: "update_vars_*"
  var:
    MSG: "from_v2_process"
    extra: "EXTRA"
""")

        pA = Process(
            name="update_vars_proc",
            script="#!/bin/bash\necho {{MSG}}\necho {{other}}\necho {{extra}}\necho {{org}}",
            var={"org": "Original"},
            logs_directory="logs_test_update_vars"
        )

        # Update from a list of files; v2 should override MSG; extra should appear; "org" kept
        pA.update_vars([v1, v2])
        pA.execute()
        Process.wait(pA.hash)

        outA = pA.get_output()
        assert "from_v2_process" in outA, "❌ MSG from process-scoped v2 not applied"
        assert "X1" in outA, "❌ 'other' from v1 (global) not applied"
        assert "EXTRA" in outA, "❌ 'extra' from v2 not applied"
        assert "Original" in outA, "❌ inline var 'org' not preserved"

        # verify we kept track of var_file(s) as list-like (stringify is ok)
        assert pA.params.get("var_file") is not None, "❌ var_file tracking missing after list update"

    finally:
        shutil.rmtree(tmpA, ignore_errors=True)

    # ---------- B) Directory of YAMLs ----------
    tmpB = tempfile.mkdtemp(prefix="update_vars_dir_", dir=base_tmp)
    try:
        d1 = os.path.join(tmpB, "one.yaml")
        d2 = os.path.join(tmpB, "two.yml")
        with open(d1, "w") as f:
            f.write("""
A: "from_dir_1"
""")
        with open(d2, "w") as f:
            f.write("""
- scope: process
  name: "update_vars_dir_*"
  var:
    B: "from_dir_process"
""")
        # a non-yaml file should be ignored
        with open(os.path.join(tmpB, "ignore.txt"), "w") as f:
            f.write("NOPE\n")

        pB = Process(
            name="update_vars_dir_proc",
            script="#!/bin/bash\necho {{A}}\necho {{B}}",
            logs_directory="logs_test_update_vars"
        )

        pB.update_vars(tmpB)  # pass directory
        pB.execute()
        Process.wait(pB.hash)

        outB = pB.get_output()
        assert "from_dir_1" in outB, "❌ Directory YAML (A) not merged"
        assert "from_dir_process" in outB, "❌ Directory process-scoped var (B) not applied"
        assert pB.params.get("var_file") == tmpB or pB.params.get("var_file") == [tmpB], "❌ var_file tracking should reflect directory"

        print("✅ Passed: update_vars() with list and directory")
        passed += 1

    finally:
        shutil.rmtree(tmpB, ignore_errors=True)

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 18: Concurrent tail across multiple processes")
# time.sleep(0.5)
try:
    # Two processes that overlap in time and write to both stdout and stderr
    procA = Process(
        name="tail_conc_1",
        script="""#!/bin/bash
for i in {1..4}; do
    echo "A STDOUT $i"
    echo "A STDERR $i" >&2
    sleep 1
done
""",
        logs_directory="logs_test_tail_concurrent"
    )
    procB = Process(
        name="tail_conc_2",
        script="""#!/bin/bash
for j in {5..8}; do
    echo "B STDOUT $j"
    echo "B STDERR $j" >&2
    sleep 1
done
""",
        logs_directory="logs_test_tail_concurrent"
    )

    # Start both
    procA.execute()
    procB.execute()

    # Wait with concurrent tailing of BOTH streams
    ok = Process.wait(["tail_conc_1", "tail_conc_2"], tail="both", tail_poll=0.2)
    assert ok, "❌ Process.wait returned False"

    # Validate both completed successfully
    assert procA.get_exitcode().startswith("0"), "❌ tail_conc_1 exit code not 0"
    assert procB.get_exitcode().startswith("0"), "❌ tail_conc_2 exit code not 0"

    # Validate outputs were fully written
    outA, errA = procA.get_output(), procA.get_error()
    outB, errB = procB.get_output(), procB.get_error()
    assert "A STDOUT 4" in outA, "❌ tail_conc_1 stdout incomplete"
    assert "A STDERR 4" in errA, "❌ tail_conc_1 stderr incomplete"
    assert "B STDOUT 8" in outB, "❌ tail_conc_2 stdout incomplete"
    assert "B STDERR 8" in errB, "❌ tail_conc_2 stderr incomplete"

    # Backward-compatibility check: wait again with no tail (should be a no-op and not crash)
    ok2 = Process.wait(["tail_conc_1", "tail_conc_2"])
    assert ok2, "❌ Process.wait without tail unexpectedly failed"

    print("✅ Passed: Concurrent multi-process tailing (stdout+stderr) and no-tail fallback")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 19: Hash reacts deterministically (same inputs) and to allowed file changes")
# time.sleep(0.5)
try:
    # --- Setup a temp directory with inputs ---
    tmpdir = tempfile.mkdtemp(prefix="hash_inputs_", dir=base_tmp)
    p_yaml = os.path.join(tmpdir, "p.yaml")
    v_yaml = os.path.join(tmpdir, "v.yaml")
    script_py = os.path.join(tmpdir, "test.py")

    with open(p_yaml, "w") as f: f.write("A: 1\n")
    with open(v_yaml, "w") as f: f.write("B: 2\n")
    with open(script_py, "w") as f: f.write("#!/usr/bin/env python3\nprint('v1')\n")

    # ========== A) SAME INPUTS -> SAME PREFIX ==========
    pA1 = Process(
        name="hash_files_demo_A",
        param_file=tmpdir,         # only .yaml/.yml considered
        var_file=tmpdir,           # .yaml/.yml/.rc (and .env/.conf if you enabled)
        script_file=script_py
    )
    hA1 = pA1.hash[:6]

    # Another identical process: should have SAME prefix
    pA2 = Process(
        name="hash_files_demo_A",
        param_file=tmpdir,
        var_file=tmpdir,
        script_file=script_py
    )
    hA2 = pA2.hash[:6]
    assert hA1 == hA2, "❌ Same inputs should yield same 6-char prefix"

    # ========== B) NO CHANGE IN ALLOWED FILES -> PREFIX UNCHANGED ==========
    # Add a non-allowed file (e.g., .txt) to the directory; should NOT affect prefix
    with open(os.path.join(tmpdir, "note.txt"), "w") as f: f.write("this should be ignored\n")

    pA3 = Process(
        name="hash_files_demo_A",
        param_file=tmpdir,
        var_file=tmpdir,
        script_file=script_py
    )
    hA3 = pA3.hash[:6]
    assert hA3 == hA1, "❌ Adding non-allowed files should not change prefix"

    # ========== C) CHANGE ALLOWED FILE CONTENT -> PREFIX CHANGES ==========
    # Change the script_file content (always included)
    with open(script_py, "w") as f: f.write("#!/usr/bin/env python3\nprint('v2')\n")

    pA4 = Process(
        name="hash_files_demo_A",
        param_file=tmpdir,
        var_file=tmpdir,
        script_file=script_py
    )
    hA4 = pA4.hash[:6]
    assert hA4 != hA1, "❌ Changing script_file content should change prefix"

    # Also change an allowed YAML (var/param) file content; should change again
    with open(v_yaml, "w") as f: f.write("B: 999\n")

    pA5 = Process(
        name="hash_files_demo_A",
        param_file=tmpdir,
        var_file=tmpdir,
        script_file=script_py
    )
    hA5 = pA5.hash[:6]
    assert hA5 != hA4, "❌ Changing allowed YAML content should change prefix again"

    # ========== D) NO param_file / var_file / script_file ==========
    # Same inline script -> same prefix
    pB1 = Process(name="hash_no_files", script="#!/bin/bash\necho hi\n")
    pB2 = Process(name="hash_no_files", script="#!/bin/bash\necho hi\n")
    hB1, hB2 = pB1.hash[:6], pB2.hash[:6]
    assert hB1 == hB2, "❌ Same params without files should yield same prefix"

    # Change inline script -> prefix changes
    pB3 = Process(name="hash_no_files", script="#!/bin/bash\necho bye\n")
    hB3 = pB3.hash[:6]
    assert hB3 != hB1, "❌ Changing inline script should change prefix"

    print("✅ Passed: Hash stability and sensitivity across files, dirs, and inline script")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass


print("\n>>> Test 20: Parallelism True vs False (robust overlap via markers)")

try:
    logs_dir = "logs_test_parallel"
    os.makedirs(logs_dir, exist_ok=True)
    sync_dir = os.path.abspath(logs_dir)

    def parallel_handshake(label, other, sync_dir, timeout=30):
        return f"""#!/bin/bash
set -euo pipefail
mkdir -p "{sync_dir}"
touch "{sync_dir}/{label}.started"

# Wait for the other job to start (proves overlap)
for i in $(seq 1 {timeout}); do
  [[ -f "{sync_dir}/{other}.started" ]] && break
  sleep 1
done

[[ -f "{sync_dir}/{other}.started" ]] || (echo "NO_OVERLAP: {other} never started" >&2; exit 42)

# Do a little work so both are "alive" together
for i in {{1..3}}; do
  echo "{label} $i"
  sleep 1
done
"""

    def serial_script_C(sync_dir):
        return f"""#!/bin/bash
set -euo pipefail
mkdir -p "{sync_dir}"
rm -f "{sync_dir}/C.done" "{sync_dir}/SERIAL_OVERLAP"
for i in {{1..3}}; do
  echo "C $i"
  sleep 1
done
touch "{sync_dir}/C.done"
"""

    def serial_script_D(sync_dir):
        return f"""#!/bin/bash
set -euo pipefail
mkdir -p "{sync_dir}"
# If D starts before C finishes, fail deterministically
[[ -f "{sync_dir}/C.done" ]] || (echo "SERIAL_OVERLAP" | tee "{sync_dir}/SERIAL_OVERLAP" >&2; exit 43)

for i in {{1..3}}; do
  echo "D $i"
  sleep 1
done
"""

    # Clean markers from previous runs
    for f in ("A.started", "B.started", "C.done", "SERIAL_OVERLAP"):
        try:
            os.remove(os.path.join(sync_dir, f))
        except FileNotFoundError:
            pass

    # --------------- A) parallel=True: handshake must succeed ---------------
    pA = Process(name="parallel_true_A", script=parallel_handshake("A", "B", sync_dir), logs_directory=logs_dir)
    pB = Process(name="parallel_true_B", script=parallel_handshake("B", "A", sync_dir), logs_directory=logs_dir)

    t0 = time.time()
    pA.execute()
    pB.execute()
    Process.wait([pA.hash, pB.hash])
    t1 = time.time()
    elapsed_parallel = t1 - t0

    assert pA.get_exitcode().startswith("0"), f"❌ parallel=True: A exit code non-zero\n{pA.get_output()}"
    assert pB.get_exitcode().startswith("0"), f"❌ parallel=True: B exit code non-zero\n{pB.get_output()}"

    # --------------- B) parallel=False: D must see C.done at start ---------------
    pC = Process(name="parallel_false_C", script=serial_script_C(sync_dir), logs_directory=logs_dir, parallel=False)
    pD = Process(name="parallel_false_D", script=serial_script_D(sync_dir), logs_directory=logs_dir, parallel=False)

    t2 = time.time()
    pC.execute()
    pD.execute()
    Process.wait([pC.hash, pD.hash])
    t3 = time.time()
    elapsed_serial = t3 - t2

    assert pC.get_exitcode().startswith("0"), f"❌ parallel=False: C exit code non-zero\n{pC.get_output()}"
    assert pD.get_exitcode().startswith("0"), f"❌ parallel=False: D exit code non-zero\n{pD.get_output()}"

    # Deterministic overlap detector for serial case
    assert not os.path.exists(os.path.join(sync_dir, "SERIAL_OVERLAP")), \
        "❌ parallel=False: detected overlap (D started before C finished)"

    # --------------- Optional timing (loose, to avoid Slurm flakiness) ---------------
    # Only enforce if serial is meaningfully larger (otherwise just print)
    if elapsed_serial > 6:
        assert elapsed_parallel < elapsed_serial, (
            f"❌ Expected parallel < serial (parallel={elapsed_parallel:.1f}s, serial={elapsed_serial:.1f}s)"
        )

    print(f"✅ Passed: parallel={elapsed_parallel:.1f}s, serial={elapsed_serial:.1f}s")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 21: always_run ignores global stop (runs after upstream failure)")
try:
    Process.reset_stop()

    # Failing upstream (sets global stop in backends)
    up = Process(
        name="ar_fail_up",
        script="#!/bin/bash\nexit 3",
        logs_directory="logs_ar"
    )
    try:
        up.execute()
        Process.wait(up.hash)
    except RuntimeError:
        pass

    # Normally this would be skipped due to global stop; always_run makes it launch
    dn = Process(
        name="ar_dn",
        script="#!/bin/bash\necho 'I ran'",
        depends_on=["ar_fail_up"],
        always_run=True,
        logs_directory="logs_ar"
    )
    dn.execute()
    Process.wait(dn.hash)
    assert dn.get_exitcode().startswith("0"), "❌ always_run should run despite global stop"
    print("✅ Passed: always_run runs despite global stop")

    # always_run does not override when
    p = Process(
        name="ar_when_false",
        script="#!/bin/bash\necho nope",
        when=False,
        always_run=True,
        logs_directory="logs_ar"
    )
    p.execute()
    assert p.finished_event.is_set() and p.get_exitcode() is None, "❌ 'when=False' should still skip"
    print("✅ Passed: always_run respects 'when'")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 22: allow_skipped_deps — default allows skip, strict blocks")
# time.sleep(0.5)
try:
    Process.reset_stop()

    # --- A) Default behavior (allow_skipped_deps=True): downstream runs if upstream is skipped
    upA = Process(
        name="askip_up_A",
        script="#!/bin/bash\necho UP\n",
        when=False,  # upstream is skipped
        logs_directory="logs_allow_skip"
    )
    upA.execute()

    dnA = Process(
        name="askip_dn_A",
        script="#!/bin/bash\necho DN\n",
        depends_on=["askip_up_A"],  # default allow_skipped_deps=True
        logs_directory="logs_allow_skip"
    )
    dnA.execute()
    Process.wait(dnA.hash)
    assert dnA.get_exitcode().startswith("0"), "❌ Default should allow skipped dependency"
    print("✅ Subtest A passed: default allows skipped deps")

    # --- B) Strict behavior (allow_skipped_deps=False): downstream is blocked on skipped upstream
    Process.reset_stop()

    upB = Process(
        name="askip_up_B",
        script="#!/bin/bash\necho UP\n",
        when=False,  # upstream is skipped again
        logs_directory="logs_allow_skip"
    )
    upB.execute()

    dnB = Process(
        name="askip_dn_B",
        script="#!/bin/bash\necho DN\n",
        depends_on=["askip_up_B"],
        allow_skipped_deps=False,  # strict: require success; skip is not allowed
        logs_directory="logs_allow_skip"
    )
    dnB.execute()
    Process.wait(dnB.hash)
    assert dnB.finished_event.is_set(), "❌ Strict mode: downstream should be marked finished (skipped)"
    assert dnB.get_exitcode() is None, "❌ Strict mode: downstream should not have an exit code"
    print("✅ Subtest B passed: strict blocks when upstream is skipped")

    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 23: Auto mk./map. vars mount for apptainer, docker, kubernetes")
# time.sleep(0.5)
try:
    # prepare a simple directory and input file
    tmp_dir = tempfile.mkdtemp(prefix="auto_mount_test_", dir=base_tmp)
    mk_dir = os.path.join(tmp_dir, "out")
    map_file = os.path.join(tmp_dir, "in.txt")
    with open(map_file, "w") as f:
        f.write("HelloFromMap\n")

    common = dict(
        name="auto_mount_test",
        script="""#!/bin/bash
echo "OUTDIR={{mk.outdir}}"
cat {{map.infile}}
""",
        var={"mk.outdir": mk_dir, "map.infile": map_file},
        logs_directory="logs_test_auto_mount"
    )

    ran = False

    # --------- mk.* should mkdir regardless of automated_mount ----------
    mk_dir_true = os.path.join(tmp_dir, "out_auto_true")
    p_local_true = Process(
        name="mk_always_true",
        script="#!/bin/bash\necho {{mk.outdir}}\n",
        var={"mk.outdir": mk_dir_true},
        logs_directory="logs_test_auto_mount",
        automated_mount=True
    )
    p_local_true.execute()
    time.sleep(5)
    Process.wait(p_local_true.hash)
    assert os.path.isdir(mk_dir_true), "❌ mk.* did not create dir with automated_mount=True"

    mk_dir_false = os.path.join(tmp_dir, "out_auto_false")
    p_local_false = Process(
        name="mk_always_false",
        script="#!/bin/bash\necho ok\n",
        var={"mk.outdir": mk_dir_false},
        logs_directory="logs_test_auto_mount",
        automated_mount=False
    )
    p_local_false.execute()
    Process.wait(p_local_false.hash)
    assert os.path.isdir(mk_dir_false), "❌ mk.* did not create dir with automated_mount=False"
    # -------------------------------------------------------------------------

    if utils.docker_available():
        print("   [docker] running...")
        pD = Process(**{**common, "environment": "docker", "container": "ubuntu:22.04"})
        pD.execute()
        Process.wait(pD.hash)
        assert pD.get_exitcode().startswith("0"), "❌ Docker auto-mount failed"
        ran = True

    if utils.apptainer_available():
        print("   [apptainer] running...")
        pA = Process(**{**common, "environment": "apptainer", "container": "ubuntu:22.04"})
        pA.execute()
        Process.wait(pA.hash)
        assert pA.get_exitcode().startswith("0"), "❌ Apptainer auto-mount failed"
        ran = True

    if utils.kubernetes_available():
        print("   [kubernetes] generating manifest...")
        pK = Process(**{**common, "manager": "kubernetes", "container": "ubuntu:22.04"})
        manifest_path = pK._generate_k8s_manifest()
        assert os.path.exists(manifest_path), "❌ K8s manifest not created"
        with open(manifest_path) as f:
            manifest_json = f.read()
        assert "jawm-vol" in manifest_json, "❌ K8s auto volume missing"
        ran = True

    if not ran:
        print("   Skipped container runs (no container backend available or manager is slurm)")

    print("✅ Passed: Auto mk./map. vars mount + mk.* mkdir independent of automated_mount")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 24: Hashing via -p (scope: hash): new → mismatch(no overwrite) → overwrite(true) → reference check")

try:

    def cli_cmd(args):
        if shutil.which("jawm"):
            return ["jawm", *args]
        return [sys.executable, "-m", "jawm.cli", *args]

    def run_cli(args, timeout=45, cwd=None):
        r = subprocess.run(cli_cmd(args), capture_output=True, text=True, timeout=timeout, cwd=cwd)
        both = (r.stdout or "") + (r.stderr or "")
        return r.returncode, r.stdout, r.stderr, both

    def tail(path):
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().splitlines() if ln.strip()]
        return lines[-1] if lines else None

    root = tempfile.mkdtemp(prefix="cli_hash_p_scope_", dir=base_tmp)
    wf = os.path.join(root, "wf"); os.makedirs(wf, exist_ok=True)

    # trivial workflow
    main_py = os.path.join(wf, "main.py")
    with open(main_py, "w", encoding="utf-8") as f:
        f.write("print('WF RUN v1')\n")

    # params with scope: hash
    params_yaml = os.path.join(wf, "params.yaml")
    with open(params_yaml, "w", encoding="utf-8") as f:
        f.write(f"""- scope: hash
  include:
    - {main_py}
  allowed_extensions: ["py"]
  exclude_dirs: ["__pycache__", ".mypy_cache", ".ipynb_checkpoints", "jawm_runs", "jawm_hashes"]
  exclude_files: ["*.tmp", "*.swp"]
  recursive: true
  overwrite: false
""")

    logs_dir = os.path.join(wf, "logs")
    hashes_dir = os.path.join(logs_dir, "jawm_hashes")
    wf_stem = "main"  # from main.py
    hash_file = os.path.join(hashes_dir, f"{wf_stem}.hash")
    input_hist = os.path.join(hashes_dir, f"{wf_stem}_input.history")
    user_hist  = os.path.join(hashes_dir, f"{wf_stem}_user_defined.history")

    # 24.1 First run — expect:
    # - input.history appended
    # - <wf>.hash created from user-defined config
    # - user_defined.history appended
    rc, _, _, both = run_cli([wf, "-l", "logs", "-p", "params.yaml"], cwd=wf)
    assert rc == 0, f"❌ first run failed\n{both}"
    assert os.path.isfile(input_hist), "❌ <wf>_input.history missing"
    assert os.path.isfile(hash_file), "❌ <wf>.hash missing after first run"
    assert os.path.isfile(user_hist), "❌ <wf>_user_defined.history missing"
    with open(hash_file, "r", encoding="utf-8") as f: h1 = f.read().strip()
    assert re.fullmatch(r"[0-9a-f]{64}", h1), f"❌ invalid hex in hash file: {h1}"
    last_user = tail(user_hist); assert last_user, "❌ user_defined.history empty"
    assert last_user.split("\t")[1] == h1, "❌ user_defined.history hash != stored hash"

    # 24.2 Change workflow → mismatch (overwrite=false)
    with open(main_py, "w", encoding="utf-8") as f:
        f.write("print('WF RUN v2')\n")
    rc, _, _, both = run_cli([wf, "-l", "logs", "-p", "params.yaml"], cwd=wf)
    assert rc == 0, f"❌ second run failed (no-overwrite)\n{both}"
    with open(hash_file, "r", encoding="utf-8") as f: h2_stored = f.read().strip()
    assert h2_stored == h1, "❌ stored hash changed despite overwrite=false"
    last_user2 = tail(user_hist); assert last_user2, "❌ user_defined.history not appended"
    new_run_hash = last_user2.split("\t")[1]
    assert new_run_hash != h1, "❌ user_defined.history did not capture new computed hash"

    # 24.3 overwrite=true → stored hash must update to new computed value
    with open(params_yaml, "a", encoding="utf-8") as f:
        f.write("  overwrite: true\n")
    rc, _, _, both = run_cli([wf, "-l", "logs", "-p", "params.yaml"], cwd=wf)
    assert rc == 0, f"❌ third run failed (overwrite)\n{both}"
    with open(hash_file, "r", encoding="utf-8") as f: h3 = f.read().strip()
    last_user3 = tail(user_hist); assert last_user3, "❌ user_defined.history not appended (overwrite run)"
    computed_now = last_user3.split("\t")[1]
    assert h3 == computed_now, "❌ stored hash not updated to latest computed hash"
    assert h3 != h1, "❌ stored hash should differ from original after overwrite=true"

    # 24.4 reference check:
    #   - lock reference to current stored hash (h3) → run ok
    #   - change workflow again → expect exit code 73 (mismatch)
    with open(params_yaml, "a", encoding="utf-8") as f:
        f.write(f"  reference: \"sha256:{h3}\"\n")
    rc, _, _, both = run_cli([wf, "-l", "logs", "-p", "params.yaml"], cwd=wf)
    assert rc == 0, f"❌ reference matched run failed\n{both}"

    # change input so new user-defined hash ≠ h3
    with open(main_py, "w", encoding="utf-8") as f:
        f.write("print('WF RUN v3')\n")
    rc, _, _, both = run_cli([wf, "-l", "logs", "-p", "params.yaml"], cwd=wf)
    assert rc == 73, f"❌ expected exit 73 on reference mismatch, got {rc}\n{both}"
    # ensure user_defined.history appended even on mismatch
    last_user4 = tail(user_hist); assert last_user4, "❌ user_defined.history not appended on mismatch"
    assert last_user4.split("\t")[1] != h3, "❌ mismatch run did not compute a new hash"

    print("✅ Passed: Test 24 (-p scope: hash) new → mismatch → overwrite → reference check")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    shutil.rmtree(root, ignore_errors=True)


print("\n>>> Test 25: update_params invalidates cached script (var re-substitution)")
try:
    # workspace
    tmpdir = tempfile.mkdtemp(prefix="upd_params_", dir=base_tmp)
    logs = os.path.join(tmpdir, "logs")
    os.makedirs(logs, exist_ok=True)
    yaml_path = os.path.join(tmpdir, "params.yaml")

    # YAML that provides var.ncores
    with open(yaml_path, "w") as f:
        f.write("""
- scope: process
  name: "upd_params_case"
  var:
    ncores: "8"
""")

    # Process with unresolved {{ncores}} initially
    p = Process(
        name="upd_params_case",
        script="""#!/bin/bash
echo "fastqc -t {{ncores}}"
""",
        logs_directory=logs
    )

    # 1) First run (no vars yet): placeholder should be visible in output
    p.execute()
    Process.wait(p.hash)
    out1 = p.get_output() or ""
    assert "{{ncores}}" in out1, "❌ Expected unresolved placeholder in first run output"

    # 2) Update params to provide var.ncores, then run again
    p.update_params(yaml_path)
    p.execute()
    Process.wait(p.hash)
    out2 = p.get_output() or ""
    script2 = p.get_script() or ""

    # Should now be substituted everywhere
    assert "fastqc -t 8" in out2, "❌ ncores not substituted in second run output"
    assert "{{ncores}}" not in out2, "❌ Placeholder still present in second run output"
    assert "fastqc -t 8" in script2, "❌ ncores not substituted in regenerated base script"

    print("✅ Passed: update_params triggers base script regeneration and var substitution")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    try:
        shutil.rmtree(tmpdir, ignore_errors=True)
    except Exception:
        pass



print("\n>>> Test 26: Deep-merge (constructor) for var/env/manager_slurm/environment_docker")
Process.reset_stop()
_clear_params()

tmp = None
try:
    os.environ["JAWM_EXPAND_PATH"] = "FALSE"
    tmp = tempfile.mkdtemp(prefix="merge_ctor_", dir=base_tmp)
    params_yaml = os.path.join(tmp, "params.yaml")

    with open(params_yaml, "w") as f:
        f.write("""
- scope: global
  var: { A: 1, B: 2, mk.output: "./out" }
  env: { X: "globalX" }
  manager_slurm: { "-p": "cluster", "--mem": "4G" }
  environment_docker: { "--cpus": "1.0" }

- scope: process
  name: "merge_ctor_proc"
  var: { B: 20, C: 3 }
  env: { Y: "procY" }
  manager_slurm: { "--mem": "8G", "-t": "00:05:00" }
  environment_docker: { "--cpus": "2.0", "--uts": "host" }
""")

    p = Process(
        name="merge_ctor_proc",
        param_file=params_yaml,
        script="#!/bin/bash\necho ok\n",
        logs_directory=os.path.join(tmp, "logs"),
    )

    # var merged: process overrides B, keeps A and adds C, preserves global mk.output
    exp = {"A": 1, "B": 20, "C": 3, "mk.output": "./out"}
    assert all(p.var.get(k) == v for k, v in exp.items()), f"var merge wrong (missing/incorrect): {p.var}"
    # alias must also be present now
    assert p.var.get("output") == "./out", f"alias 'output' missing or wrong: {p.var}"

    # env merged
    assert p.env.get("X") == "globalX" and p.env.get("Y") == "procY", f"env merge wrong: {p.env}"

    # manager_slurm merged (global -p kept, --mem overridden, -t added)
    ms = p.manager_slurm or {}
    assert ms.get("-p") == "cluster", f"slurm -p lost: {ms}"
    assert ms.get("--mem") == "8G", f"slurm --mem override not applied: {ms}"
    assert ms.get("-t") == "00:05:00", f"slurm -t missing: {ms}"

    # environment_docker merged (global --cpus overridden to 2.0, --uts added)
    ed = p.environment_docker or {}
    assert ed.get("--cpus") == "2.0" and ed.get("--uts") == "host", f"docker env merge wrong: {ed}"

    print("✅ Passed: Deep-merge at constructor for multiple dict fields")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    os.environ.pop("JAWM_EXPAND_PATH", None)
    if tmp and os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    
    _restore_params(bak_default, bak_override)



print("\n>>> Test 27: Deep-merge on update_params() without clobbering existing dicts")
Process.reset_stop()
_clear_params()

tmp = None
try:
    tmp = tempfile.mkdtemp(prefix="merge_update_", dir=base_tmp)

    # Initial params (simulate first load)
    params1 = os.path.join(tmp, "params1.yaml")
    with open(params1, "w") as f:
        f.write("""
- scope: global
  var: { G: "g", KEEP: "k" }
  manager_slurm: { "-p": "gcluster", "--mem": "2G" }

- scope: process
  name: "merge_up_proc"
  var: { PONLY: 1 }
  manager_slurm: { "-t": "00:02:00" }
""")

    p = Process(
        name="merge_up_proc",
        param_file=params1,
        script="#!/bin/bash\necho ok\n",
        logs_directory=os.path.join(tmp, "logs"),
    )

    # Sanity on initial merge
    assert p.var.get("G") == "g" and p.var.get("KEEP") == "k" and p.var.get("PONLY") == 1, f"initial var wrong: {p.var}"
    ms = p.manager_slurm or {}
    assert ms.get("-p") == "gcluster" and ms.get("--mem") == "2G" and ms.get("-t") == "00:02:00", f"initial slurm wrong: {ms}"

    # Now update with params2: add/override some keys; ensure deep-merge, not replace
    params2 = os.path.join(tmp, "params2.yaml")
    with open(params2, "w") as f:
        f.write("""
- scope: global
  var: { G: "g2", NEWG: "ng" }
  manager_slurm: { "--mem": "6G" }

- scope: process
  name: "merge_up_proc"
  var: { PONLY: 99, PNEW: "pn" }
  manager_slurm: { "-t": "00:10:00" }
""")

    p.update_params(params2)

    # var after update: global(G->g2, adds NEWG), process(PONLY->99 keeps), KEEP remains from first load
    assert p.var == {"G": "g2", "KEEP": "k", "PONLY": 99, "PNEW": "pn", "NEWG": "ng"}, f"var deep-merge after update wrong: {p.var}"

    # manager_slurm after update: -p kept, --mem overridden to 6G (global), -t overridden to 00:10:00 (process)
    ms2 = p.manager_slurm or {}
    assert ms2.get("-p") == "gcluster", f"slurm -p lost after update: {ms2}"
    assert ms2.get("--mem") == "6G", f"slurm --mem not updated: {ms2}"
    assert ms2.get("-t") == "00:10:00", f"slurm -t not updated: {ms2}"

    print("✅ Passed: Deep-merge on update_params() preserves/overrides as expected")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    if tmp and os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
    _restore_params(bak_default, bak_override)


print("\n>>> Test 28: clone — same hash prefix when unchanged; different when a param is modified")
Process.reset_stop()
_clear_params()
try:
    # Create a minimal process
    p0 = Process(
        name="clone_hash_src0",
        script="#!/bin/bash\necho hi",
        var={"A": 1},
        logs_directory="logs_test_clone_hash"
    )

    p1 = p0.clone(name="clone_hash_src_norm")

    # Direct clone without changing anything → same 6-char prefix
    p2 = p1.clone()
    prefix1 = p1.hash[:6]
    prefix2 = p2.hash[:6]
    assert prefix1 == prefix2, (
        f"❌ Expected identical hash prefixes for unchanged clone, "
        f"got {prefix1} vs {prefix2}"
    )

    # Modify a declared param after init → different 6-char prefix
    p1.manager = "slurm"  # tracked via __setattr__/_touched_params
    p3 = p1.clone(name="clone_hash_copy_changed")
    prefix3 = p3.hash[:6]
    assert prefix3 != prefix1, (
        f"❌ Expected different hash prefix after changing 'manager', "
        f"but got same prefix {prefix3}"
    )

    # Values carried as intended
    assert p2.manager == "local", "❌ Unchanged clone should keep default manager"
    assert p3.manager == "slurm", "❌ Changed 'manager' not carried to clone"

    print(
        f"✅ Passed: prefixes — unchanged {prefix1} == {prefix2}; "
        f"changed {prefix1} != {prefix3}"
    )
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    _restore_params(bak_default, bak_override)


print("\n>>> Test 29: CLI var injection sanitizes mk./map. and Process still resolves originals")
try:
    # --- Helper functions ---
    def cli_cmd(args):
        if shutil.which("jawm"):
            return ["jawm", *args]
        return [sys.executable, "-m", "jawm.cli", *args]

    def run_cli(args, timeout=60):
        r = subprocess.run(cli_cmd(args), capture_output=True, text=True, timeout=timeout)
        both = (r.stdout or "") + (r.stderr or "")
        return r.returncode, r.stdout, r.stderr, both

    # --- Temporary working directory ---
    tmp_root = tempfile.mkdtemp(prefix="cli_sanitize_", dir=base_tmp)
    try:
        mod_dir = os.path.join(tmp_root, "mod")
        os.makedirs(mod_dir, exist_ok=True)

        # Variables file containing mk.* and map.* keys (and a normal key)
        vars_path = os.path.join(mod_dir, "vars.yaml")
        with open(vars_path, "w") as f:
            f.write(
                "- scope: global\n"
                "  var:\n"
                "    mk.output: \"cli_out_dir\"\n"
                "    map.infile: \"cli_input.txt\"\n"
                "    NORMAL: \"NVAL\"\n"
            )

        # Create the referenced input file
        in_file = os.path.join(mod_dir, "cli_input.txt")
        with open(in_file, "w") as f:
            f.write("DATA\n")

        # Module script that prints injected vars and runs a Process
        main_py = os.path.join(mod_dir, "main.py")
        with open(main_py, "w") as f:
            f.write(
                "from jawm import Process\n"
                "print('SAN_OUT=', output)\n"
                "print('SAN_INFILE=', infile)\n"
                "print('NORMAL=', NORMAL)\n"
                "p = Process(\n"
                "    name='cli_sanitize_proc',\n"
                "    script='''#!/bin/bash\\n"
                "echo \"P_OUT={{mk.output}}\"\\n"
                "echo \"P_IN={{map.infile}}\"\\n"
                "''',\n"
                "    logs_directory='logs_cli_sanitize'\n"
                ")\n"
                "p.execute()\n"
                "Process.wait(p.hash)\n"
                "print('P_STDOUT_BEGIN')\n"
                "print(p.get_output())\n"
                "print('P_STDOUT_END')\n"
            )

        # --- Run CLI ---
        rc, out, err, both = run_cli([mod_dir, "-v", vars_path])

        # --- Assertions ---
        assert rc == 0, f"❌ CLI failed (rc={rc})\nSTDOUT:\n{out}\nSTDERR:\n{err}"

        # 1) Sanitized variables visible in executed module's globals
        assert "SAN_OUT= cli_out_dir" in both, "❌ Sanitized 'output' not injected"
        assert "SAN_INFILE= cli_input.txt" in both, "❌ Sanitized 'infile' not injected"
        assert "NORMAL= NVAL" in both, "❌ Normal variable not injected"

        # 2) Process still resolves original placeholders
        start = both.find("P_STDOUT_BEGIN")
        end = both.find("P_STDOUT_END", start)
        assert start != -1 and end != -1, "❌ Missing Process stdout markers"
        proc_stdout = both[start:end]
        assert "P_OUT=cli_out_dir" in proc_stdout, "❌ {{mk.output}} not resolved"
        assert "P_IN=cli_input.txt" in proc_stdout, "❌ {{map.infile}} not resolved"

        print("✅ Passed: CLI sanitation (mk./map.) + Process placeholder resolution")
        passed += 1

    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 30: mk./map. aliasing — mkdir, placeholder resolution, and update_vars consistency (no YAML import)")
time.sleep(0.5)
try:
    tmp = tempfile.mkdtemp(prefix="aliasing_test_", dir=base_tmp)
    try:
        # ---------- 1️⃣ Inline mk./map. ----------
        outdir = os.path.join(tmp, "out_inline")
        infile = os.path.join(tmp, "in_inline.txt")
        with open(infile, "w") as f:
            f.write("INLINE_DATA\n")

        p_inline = Process(
            name="alias_inline_proc",
            script="""#!/bin/bash
echo "OUTDIR={{outdir}}"
echo "INFILE=$(cat {{infile}})"
""",
            var={"mk.outdir": outdir, "map.infile": infile},
            logs_directory="logs_test_alias"
        )
        p_inline.execute()
        Process.wait(p_inline.hash)

        # mk.* created dir
        assert os.path.isdir(outdir), "❌ mk.* directory not created for inline var"

        # short aliases resolved
        out_inline = p_inline.get_output()
        assert f"OUTDIR={outdir}" in out_inline, "❌ {{outdir}} alias not resolved"
        assert "INFILE=INLINE_DATA" in out_inline.replace("\r", "").replace("\n", ""), "❌ {{infile}} alias not resolved"

        # both alias and prefixed keys accessible
        assert p_inline.var["outdir"] == outdir, "❌ alias key missing in proc.var"
        assert p_inline.var["mk.outdir"] == outdir, "❌ prefixed mk.* key missing in proc.var"

        print("✅ Subtest 1 (inline var) passed")

        # ---------- 2️⃣ var_file YAML (written manually) ----------
        outdir_yaml = os.path.join(tmp, "out_yaml")
        infile_yaml = os.path.join(tmp, "in_yaml.txt")
        with open(infile_yaml, "w") as f:
            f.write("YAML_DATA\n")

        var_yaml = os.path.join(tmp, "vars.yaml")
        # Simple YAML text — no yaml import required
        with open(var_yaml, "w") as f:
            f.write(f"mk.dir: {outdir_yaml}\nmap.file: {infile_yaml}\n")

        p_yaml = Process(
            name="alias_varfile_proc",
            script="""#!/bin/bash
echo "DIR={{dir}}"
echo "FILE=$(cat {{file}})"
""",
            var_file=var_yaml,
            logs_directory="logs_test_alias"
        )
        p_yaml.execute()
        Process.wait(p_yaml.hash)

        # mk.* created dir from YAML
        assert os.path.isdir(outdir_yaml), "❌ mk.* directory not created from var_file"

        out_yaml = p_yaml.get_output()
        assert f"DIR={outdir_yaml}" in out_yaml, "❌ {{dir}} alias not resolved from YAML"
        assert "FILE=YAML_DATA" in out_yaml.replace("\r", "").replace("\n", ""), "❌ {{file}} alias not resolved from YAML"

        # alias and prefixed keys coexist
        assert p_yaml.var["dir"] == outdir_yaml, "❌ alias 'dir' missing in proc.var after var_file"
        assert p_yaml.var["mk.dir"] == outdir_yaml, "❌ prefixed 'mk.dir' missing in proc.var after var_file"

        print("✅ Subtest 2 (var_file YAML) passed")

        # ---------- 3️⃣ update_vars() adds aliases ----------
        base_dir = os.path.join(tmp, "base_dir")
        upd_dir = os.path.join(tmp, "upd_dir")
        os.makedirs(base_dir, exist_ok=True)

        p_upd = Process(
            name="alias_update_proc",
            script="""#!/bin/bash
echo "BASE={{base}}"
echo "UPD={{upd}}"
""",
            var={"base": base_dir},
            logs_directory="logs_test_alias"
        )

        var_yaml_upd = os.path.join(tmp, "upd_vars.yaml")
        with open(var_yaml_upd, "w") as f:
            f.write(f"mk.upd: {upd_dir}\n")

        # update_vars should merge, add alias, and trigger mk.*
        p_upd.update_vars(var_yaml_upd)
        p_upd.execute()
        Process.wait(p_upd.hash)

        # directory creation from mk.*
        assert os.path.isdir(upd_dir), "❌ mk.* directory not created after update_vars"

        out_upd = p_upd.get_output()
        assert f"BASE={base_dir}" in out_upd, "❌ base var not resolved after update_vars"
        assert f"UPD={upd_dir}" in out_upd, "❌ alias 'upd' not resolved after update_vars"

        # alias and prefixed key must both exist
        assert p_upd.var["upd"] == upd_dir, "❌ alias 'upd' missing after update_vars"
        assert p_upd.var["mk.upd"] == upd_dir, "❌ prefixed 'mk.upd' missing after update_vars"

        print("✅ Subtest 3 (update_vars) passed")

        print("✅ Passed: Test 30 — mk./map. aliasing works across inline var, YAML, and update_vars")
        passed += 1

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
except Exception as e:
    print(f"❌ Failed: Test 30 — {e}")
    failed += 1


print("\n>>> Test 31: execute(depends_on=...) — runtime dependency override")
try:
    tmp = tempfile.mkdtemp(prefix="exec_dep_override_", dir=base_tmp)
    try:
        # Step A (upstream)
        pA = Process(
            name="exec_dep_up",
            script="""#!/bin/bash
echo "Step A complete"
""",
            logs_directory=os.path.join(tmp, "logs")
        )

        # Step B (downstream, no static depends_on)
        pB = Process(
            name="exec_dep_dn",
            script="""#!/bin/bash
echo "Step B complete"
""",
            logs_directory=os.path.join(tmp, "logs")
        )

        # 1️⃣ Run upstream normally
        pA.execute()
        Process.wait(pA.hash)
        assert pA.get_exitcode().startswith("0"), "❌ Upstream process failed unexpectedly"

        # 2️⃣ Now call execute() on downstream with runtime dependency override
        pB.execute(["exec_dep_up"])
        Process.wait(pB.hash)

        # Ensure downstream was registered and executed after dependency completion
        assert pB.get_exitcode().startswith("0"), "❌ Downstream process did not run successfully"
        assert "Step B complete" in pB.get_output(), "❌ Downstream output missing"

        # 3️⃣ Confirm that the runtime override actually took effect
        assert pB.depends_on == ["exec_dep_up"], f"❌ Runtime depends_on override not applied: {pB.depends_on}"

        print("✅ Passed: execute(depends_on=...) overrides dependencies at runtime")
        passed += 1

    finally:
        shutil.rmtree(tmp, ignore_errors=True)
except Exception as e:
    print(f"❌ Failed: Test 31 — {e}")
    failed += 1


# ======================================================
# Test for dependency scheduling including parallel
# ======================================================

print("\n>>> Test 32: Non-blocking deps with parallel=True (loop should not serialize)")

tmp_root = tempfile.mkdtemp(prefix="nbdeps_", dir=base_tmp)
try:
    N = 3
    mapping_sleep = 2  # seconds
    mappings, flagstats = [], []

    def mapping_script(i, root):
        return f"""#!/bin/bash
echo "M_START {i} $(date +%s)"
sleep {mapping_sleep}
echo "done" > "{root}/done_{i}.txt"
echo "M_END {i} $(date +%s)"
"""

    def flagstat_script(i, root):
        return f"""#!/bin/bash
echo "F_START {i} $(date +%s)"
if [ ! -f "{root}/done_{i}.txt" ]; then
  echo "MARKER_MISSING {i}"
  exit 2
fi
cat "{root}/done_{i}.txt"
echo "F_END {i} $(date +%s)"
"""

    t0 = time.time()
    for i in range(1, N + 1):
        m = Process(
            name=f"nbdep_map_{i}",
            script=mapping_script(i, tmp_root),
            logs_directory="logs_nbdeps"
        )
        f = Process(
            name=f"nbdep_flag_{i}",
            script=flagstat_script(i, tmp_root),
            logs_directory="logs_nbdeps"
        )
        m.execute()
        f.execute(depends_on=m.hash)
        mappings.append(m)
        flagstats.append(f)

    # Ensure the loop returns quickly (non-blocking)
    schedule_elapsed = time.time() - t0
    assert schedule_elapsed < (N * mapping_sleep * 0.7), (
        f"❌ Scheduling loop took too long ({schedule_elapsed:.2f}s)"
    )

    Process.wait([p.hash for p in (mappings + flagstats)])

    # Validate all succeeded and marker files were read
    for i, (m, f) in enumerate(zip(mappings, flagstats), start=1):
        assert m.get_exitcode().startswith("0"), f"❌ mapping_{i} failed"
        assert f.get_exitcode().startswith("0"), f"❌ flagstat_{i} failed"
        assert "done" in (f.get_output() or ""), f"❌ flagstat_{i} missing marker"

    print(f"✅ Passed: Non-blocking deps (parallel=True). Schedule time={schedule_elapsed:.2f}s")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    shutil.rmtree(tmp_root, ignore_errors=True)


print("\n>>> Test 33: parallel=False blocks caller until completion (with dependency)")
try:
    tmpdir = tempfile.mkdtemp(prefix="pfalse_", dir=base_tmp)

    m = Process(
        name="pfalse_map",
        script=f"""#!/bin/bash
echo "MAP_START $(date +%s)"
sleep 1
echo "done" > {tmpdir}/marker.txt
echo "MAP_END $(date +%s)"
""",
        logs_directory="logs_pfalse"
    )
    m.execute()

    f = Process(
        name="pfalse_flag",
        script=f"""#!/bin/bash
echo "FLAG_START $(date +%s)"
sleep 1
if [ ! -f {tmpdir}/marker.txt ]; then
  echo "MARKER_MISSING"
  exit 2
fi
echo "FLAG_END $(date +%s)"
""",
        logs_directory="logs_pfalse",
        parallel=False
    )

    t0 = time.time()
    f.execute(depends_on=m.hash)
    t1 = time.time()
    elapsed = t1 - t0

    assert elapsed >= 0.8, f"❌ parallel=False did not block (elapsed={elapsed:.2f}s)"
    assert f.get_exitcode().startswith("0"), "❌ flagstat failed"
    print(f"✅ Passed: parallel=False blocks caller (elapsed={elapsed:.2f}s)")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\n>>> Test 34: allow_skipped_deps=False blocks downstream when upstream is skipped")
try:
    tmpdir = tempfile.mkdtemp(prefix="skip_strict_", dir=base_tmp)
    Process.reset_stop()

    up = Process(
        name="skip_up_strict",
        script="#!/bin/bash\necho UP\n",
        when=False,
        logs_directory=tmpdir
    )
    up.execute()

    dn = Process(
        name="skip_dn_strict",
        script="#!/bin/bash\necho DN\n",
        depends_on=["skip_up_strict"],
        allow_skipped_deps=False,
        logs_directory=tmpdir
    )
    dn.execute()
    Process.wait([dn.hash])

    assert dn.finished_event.is_set(), "❌ downstream not marked finished"
    assert dn.get_exitcode() is None, "❌ downstream should be skipped (no exit code)"
    print("✅ Passed: strict skipped-deps handling")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\n>>> Test 35: depends_on normalization (string vs list) still works")
Process.reset_runtime()
try:
    tmpdir = tempfile.mkdtemp(prefix="normdep_", dir=base_tmp)

    m2 = Process(
        name="norm_map",
        script=f"#!/bin/bash\necho ok > {tmpdir}/marker.txt\n",
        logs_directory="logs_norm"
    )
    m2.execute()

    f2 = Process(
        name="norm_flag",
        script=f"""#!/bin/bash
test -f {tmpdir}/marker.txt || (echo MISS && exit 3)
echo HIT
""",
        logs_directory="logs_norm"
    )
    f2.execute(depends_on=m2.hash)

    Process.wait([f2.hash])

    assert f2.get_exitcode().startswith("0"), "❌ normalization failed"
    assert "HIT" in (f2.get_output() or ""), "❌ downstream did not run properly"
    print("✅ Passed: depends_on normalization (string -> list)")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\n>>> Test 36: Process.wait(), timeout, and environment behavior")
Process.reset_stop()
tmp = None
try:
    # --- Setup ---
    tmp = tempfile.mkdtemp(prefix="wait_cli_env_", dir=base_tmp)
    logs = os.path.join(tmp, "logs")
    os.makedirs(logs, exist_ok=True)

    # --- Quick process: should complete immediately ---
    p1 = Process(name="p1_quick", script="#!/bin/bash\necho quick", logs_directory=logs)
    p1.execute()
    Process.wait(p1.hash, log=False, timeout=50)
    assert p1.finished_event.is_set(), "❌ p1_quick did not finish"
    print(" ✓ Quick process completed normally")
    Process.reset_runtime()

    # --- Timeout test: should return early but finish later ---
    p2 = Process(name="p2_timeout", script="#!/bin/bash\nsleep 3", logs_directory=logs)
    p2.execute()
    t0 = time.time()
    Process.wait(p2.hash, log=False, timeout=2)
    dt = time.time() - t0
    assert dt < 2.5, f"❌ Timeout not respected (elapsed={dt:.2f}s)"
    print(f" ✓ Timeout respected (waited {dt:.1f}s, process still running)")

    # Wait for process to actually finish
    Process.wait(p2.hash, log=False, timeout=50)
    Process.reset_runtime()

    # --- Environment-based timeout: JAWM_WAIT_TIMEOUT=3 ---
    os.environ["JAWM_WAIT_TIMEOUT"] = "3"
    p3 = Process(name="p3_env", script="#!/bin/bash\nsleep 3", logs_directory=logs)
    t0 = time.time()
    p3.execute()
    Process.wait(p3.hash, log=False)
    dt = time.time() - t0
    del os.environ["JAWM_WAIT_TIMEOUT"]
    assert 2.0 <= dt <= 4.5, f"❌ Env timeout not applied (elapsed={dt:.2f}s)"
    print(f" ✓ Environment timeout respected (JAWM_WAIT_TIMEOUT=3 → waited {dt:.1f}s)")

    # --- ✅ Summary ---
    print("✅ Passed: Process.wait(), timeout, and environment behavior")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    try:
        Process.wait("all", timeout=10, log=False)
    except Exception:
        pass
    if tmp and os.path.isdir(tmp):
        shutil.rmtree(tmp, ignore_errors=True)


print("\n>>> Test 37: Path expansion logic and environment toggles")

try:
    cwd = os.getcwd()
    home = os.path.expanduser("~")

    # --- A) Default behavior (JAWM_EXPAND_PATH=true, JAWM_EXPAND_HOME=false) ---
    os.environ.pop("JAWM_EXPAND_PATH", None)
    os.environ.pop("JAWM_EXPAND_HOME", None)

    pA = Process(
        name="path_exp_default",
        script="#!/bin/bash\necho OK\n",
        var={"DATA_DIR": "./data", "ESC": r"\./keep", "HOME_DIR": "~/data"},
        logs_directory="logs_path_env_test"
    )

    assert pA.var["DATA_DIR"].startswith(cwd + os.sep), "❌ './' not expanded under default"
    assert pA.var["ESC"] == "./keep", "❌ '\\./' not preserved as literal"
    assert pA.var["HOME_DIR"].startswith("~/"), "❌ '~/...' should not expand by default"

    print("   ✓ Default expansion behavior correct")

    # --- B) Disable expansion globally ---
    os.environ["JAWM_EXPAND_PATH"] = "false"
    os.environ["JAWM_EXPAND_HOME"] = "false"

    pB = Process(
        name="path_exp_off",
        script="#!/bin/bash\necho OFF\n",
        var={"DATA_DIR": "./data", "HOME_DIR": "~/data"},
        logs_directory="logs_path_env_test"
    )

    assert pB.var["DATA_DIR"] == "./data", "❌ './' expanded despite JAWM_EXPAND_PATH=false"
    assert pB.var["HOME_DIR"] == "~/data", "❌ '~/...' expanded despite JAWM_EXPAND_HOME=false"

    print("   ✓ Global disable (env var false) works")

    # --- C) Enable only './' expansion (typical Docker/HPC safe mode) ---
    os.environ["JAWM_EXPAND_PATH"] = "true"
    os.environ["JAWM_EXPAND_HOME"] = "false"

    pC = Process(
        name="path_exp_pathonly",
        script="#!/bin/bash\necho PATHONLY\n",
        var={"DATA_DIR": "./data", "HOME_DIR": "~/data"},
        logs_directory="logs_path_env_test"
    )

    assert pC.var["DATA_DIR"].startswith(cwd + os.sep), "❌ './' not expanded when enabled"
    assert pC.var["HOME_DIR"].startswith("~/"), "❌ '~/...' should stay literal when JAWM_EXPAND_HOME=false"

    print("   ✓ Path-only expansion works (safe mode)")

    # --- D) Enable full expansion (./ + ~/) ---
    os.environ["JAWM_EXPAND_PATH"] = "true"
    os.environ["JAWM_EXPAND_HOME"] = "true"

    pD = Process(
        name="path_exp_all",
        script="#!/bin/bash\necho ALL\n",
        var={"DATA_DIR": "./data", "HOME_DIR": "~/data"},
        logs_directory="logs_path_env_test"
    )

    assert pD.var["DATA_DIR"].startswith(cwd + os.sep), "❌ './' not expanded with full mode"
    assert pD.var["HOME_DIR"].startswith(home + os.sep), "❌ '~/...' not expanded to home directory"

    print("   ✓ Full expansion mode works (./ and ~/ expanded)")

    # --- Cleanup ---
    os.environ.pop("JAWM_EXPAND_PATH", None)
    os.environ.pop("JAWM_EXPAND_HOME", None)

    print("✅ Passed: Path expansion logic and environment toggle behavior")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 38: hash_content() behavior — content-only vs name-sensitive")

try:
    tmpdir = tempfile.mkdtemp(prefix="hashcontent_", dir=base_tmp)

    # --- Setup files ---
    f1 = os.path.join(tmpdir, "a.txt")
    f2 = os.path.join(tmpdir, "b.txt")
    f3 = os.path.join(tmpdir, "c.txt")

    with open(f1, "w") as fh: fh.write("hello world\n")
    with open(f2, "w") as fh: fh.write("hello world\n")
    with open(f3, "w") as fh: fh.write("hello world!!\n")  # slightly different

    # --- A) Content-only mode ---
    h1 = utils.hash_content([f1, f2])
    h2 = utils.hash_content([f2, f1])
    h3 = utils.hash_content([f1])
    h4 = utils.hash_content([f3])

    assert h1 == h2, "❌ Hash should be order-independent in content-only mode"
    assert h1 != h3, "❌ Combined hash should differ from a single file (aggregate content)"
    assert h1 != h4, "❌ Different contents should yield different hashes"
    print("   ✓ Content-only mode works correctly")

    # --- B) Name-sensitive mode ---
    h_name_a = utils.hash_content([f1], consider_name=True)
    h_name_b = utils.hash_content([f2], consider_name=True)
    h_name_c = utils.hash_content([f3], consider_name=True)

    assert h_name_a != h_name_b, "❌ Name-sensitive mode should differ for different filenames"
    assert h_name_a != h_name_c, "❌ Different content should yield different hashes"
    print("   ✓ Name-sensitive mode differentiates filenames and contents")

    # --- C) Directory hashing consistency ---
    subdir = os.path.join(tmpdir, "nested")
    os.makedirs(subdir, exist_ok=True)
    f4 = os.path.join(subdir, "f1.txt")
    f5 = os.path.join(subdir, "f2.txt")
    with open(f4, "w") as fh: fh.write("abc")
    with open(f5, "w") as fh: fh.write("xyz")

    dir_hash_1 = utils.hash_content(subdir, consider_name=False)
    dir_hash_2 = utils.hash_content(subdir, consider_name=False)
    dir_hash_name = utils.hash_content(subdir, consider_name=True)

    assert dir_hash_1 == dir_hash_2, "❌ Hash should be consistent across runs"
    assert isinstance(dir_hash_1, str) and len(dir_hash_1) == 64, "❌ Output should be SHA256 hex digest"
    assert dir_hash_1 != dir_hash_name, "❌ Including names should change hash value"
    print("   ✓ Directory hashing stable and consistent")

    print("✅ Passed: hash_content() behavior test")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\n>>> Test 39: YAML Parsing — Multi-name and Merge Behavior")
try:
    _clear_params()
    tmpdir = tempfile.mkdtemp(prefix="test_multi_name_", dir=base_tmp)
    yaml_path = os.path.join(tmpdir, "params.yaml")

    # Create YAML file with both single-string and list names
    with open(yaml_path, "w") as f:
        f.write("""
- scope: process
  name: "p1"
  manager: "local"

- scope: process
  name: ["p1", "p2"]
  desc: "shared description"
  manager: "slurm"

- scope: process
  name: "p2"
  retries: 3
""")

    # Create two processes, p1 and p2
    p1 = Process(name="p1", script="#!/bin/bash\necho hi", param_file=yaml_path)
    p2 = Process(name="p2", script="#!/bin/bash\necho hi", param_file=yaml_path)

    # --- Assertions ---
    # p1 should merge both its single and list entries; last manager wins ("slurm")
    assert p1.manager == "slurm", f"❌ p1 manager not merged correctly, got {p1.manager}"
    assert p1.desc == "shared description", "❌ p1 did not inherit desc from list entry"

    # p2 should pick list-based + its own entry, merging manager and retries
    assert p2.manager == "slurm", f"❌ p2 manager not from list entry, got {p2.manager}"
    assert p2.desc == "shared description", "❌ p2 did not inherit desc from shared list entry"
    assert p2.retries == 3, "❌ p2 did not merge its own retries"

    print("✅ Passed: YAML list-of-names and repeated process merging works")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)


print("\n>>> Test 40: mk./map. variable alias synchronization before execution")

try:
    # --- A) Initial mk./map. alias creation ---
    pA = Process(
        name="alias_sync_A",
        script="#!/bin/bash\necho A",
        var={"mk.outDir": "logs_sync_test/mkA", "map.inFile": "data/inputA.txt"},
        logs_directory="logs_sync_test"
    )

    # Initially both aliases should exist
    assert pA.var["outDir"] == "logs_sync_test/mkA", "❌ mk.* alias not created initially"
    assert pA.var["inFile"] == "data/inputA.txt", "❌ map.* alias not created initially"

    # --- B) Mutate prefixed vars AFTER initialization ---
    pA.var["mk.outDir"] = "logs_sync_test/updated_dir"
    pA.var["map.inFile"] = "data/updated_input.txt"

    # The short keys are stale at this point (not yet synced)
    assert pA.var["outDir"] != "logs_sync_test/updated_dir", "❌ outDir updated too early (pre-execute)"
    assert pA.var["inFile"] != "data/updated_input.txt", "❌ inFile updated too early (pre-execute)"

    # --- C) Execute to trigger sync ---
    pA.execute()
    Process.wait(pA.hash)

    # After execute(), short aliases must be updated
    assert pA.var["outDir"] == "logs_sync_test/updated_dir", "❌ mk.* alias not synchronized at execute()"
    assert pA.var["inFile"] == "data/updated_input.txt", "❌ map.* alias not synchronized at execute()"

    print("✅ Passed: mk./map. aliases synchronized correctly before execution")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


print("\n>>> Test 41: Process Cloning — Independence, Alias Sync, and Param Inheritance")
_clear_params()
try:
    tmpdir = tempfile.mkdtemp(prefix="test_clone_", dir=base_tmp)
    yaml_path = os.path.join(tmpdir, "params.yaml")

    # --- A) Create YAML with a default desc and manager ---
    with open(yaml_path, "w") as f:
        f.write("""
- scope: process
  name: "prob_proc"
  desc: "YAML"
  manager_slurm:
    time: "2h"
    cpu: "2gb"
""")

    # --- B) Create initial Process from YAML + inline override ---
    p1 = Process(
        name="prob_proc",
        script="#!/bin/bash\necho test",
        param_file=yaml_path,
        desc="INLINE",
        var={"mk.inFile": "template", "category": "GOTERM_BP_FAT"},
    )

    assert p1.desc == "INLINE", f"❌ Inline override not applied (got {p1.desc})"
    assert p1.manager_slurm["time"] == "2h", "❌ manager_slurm not loaded from YAML"

    # --- C) Clone and check inheritance ---
    p2 = p1.clone()
    assert p2.desc == "INLINE", f"❌ Clone did not preserve desc correctly (got {p2.desc})"
    assert p2.manager_slurm == p1.manager_slurm, "❌ manager_slurm not preserved in clone"
    assert p2.var == p1.var, "❌ var dictionary mismatch in clone"
    assert p2 is not p1, "❌ Clone is not a new object"

    # --- D) Mutate runtime vars in clone; ensure no cross-contamination ---
    p2.var["mk.inFile"] = "new_file"
    p2.var["category"] = "KEGG_PATHWAY"

    # Ensure p1 unchanged
    assert p1.var["mk.inFile"] == "template", "❌ Parent var modified after clone change"
    assert p1.var["category"] == "GOTERM_BP_FAT", "❌ Parent var modified after clone change"

    # --- E) Ensure alias sync logic worked on clone creation ---
    assert "inFile" in p2.var, "❌ Clone did not sync mk./map. alias"
    assert p2.var["inFile"] == "template", f"❌ Alias in first clone not inherited properly (got {p2.var['inFile']})"

    # --- F) Second-level clone (clone of a clone) ---
    p3 = p2.clone()
    # p3 inherits alias values from p2 at clone time
    assert p3.var["inFile"] == "new_file", f"❌ Second clone did not inherit alias correctly (got {p3.var['inFile']})"

    # Now modify mk.inFile and manually re-sync alias as execute() would
    p3.var["mk.inFile"] = "second_clone"
    for k, v in list(p3.var.items()):
        if isinstance(k, str) and (k.startswith("mk.") or k.startswith("map.")):
            p3.var[k.split(".", 1)[-1]] = v
    assert p3.var["inFile"] == "second_clone", "❌ Alias sync failed after manual update"

    # --- G) Hash comparison ---
    assert p1.hash != p2.hash, "❌ Cloned process should have unique hash"
    assert p2.hash != p3.hash, "❌ Nested clone should also have unique hash"

    print("✅ Passed: Process cloning preserves runtime independence, syncs aliases, and inherits params correctly")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)


print("\n>>> Test 42: retry_overrides update base script per retry")
try:
    tmp_logs = tempfile.mkdtemp(prefix="retry_override_test_", dir=base_tmp)

    p = Process(
        name="retry_override_proc",
        script="""#!/bin/bash
echo "Value={{myvar}}"
exit {{myvar}}
""",
        retries=3,
        logs_directory=tmp_logs,
        var={"myvar": 1},     # Initial value
        retry_overrides={
            1: {"var": {"myvar": 2}},  # retry 1 -> exit 2
            2: {"var": {"myvar": 3}},  # retry 2 -> exit 3
            3: {"var": {"myvar": 0}},  # retry 3 -> exit 0 (success)
        }
    )

    p.execute()
    Process.wait(p.hash)

    # --- Assertions ---
    # Final exitcode MUST reflect the last retry override (myvar=0)
    assert p.get_exitcode().startswith("0"), f"❌ Final exitcode wrong, got {p.get_exitcode()}"

    # Check that each attempt actually rewrote the script with the new var
    script_path = os.path.join(p.log_path, f"{p.name}.script")
    with open(script_path, "r") as sf:
        final_script = sf.read()

    assert "exit 0" in final_script, "❌ Script was not regenerated with updated var during retries"

    print("✅ Passed: retry_overrides update vars + regenerate script per retry")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmp_logs, ignore_errors=True)


print("\n>>> Test 43: Params order check: YAML vs Python vs CLI overrides (-l, -r)")

try:
    _clear_params()

    # --- Setup temp workspace ---
    tmpdir = tempfile.mkdtemp(prefix="test_yaml_cli_priority_", dir=base_tmp)
    module_path = os.path.join(tmpdir, "test_mod.py")
    yaml_path = os.path.join(tmpdir, "params.yaml")

    # Write YAML that tries to override logs_directory and sets retries
    with open(yaml_path, "w") as f:
        f.write("""
- scope: global
  logs_directory: "from_yaml"
  retries: 7
""")

    # Python module sets logs_directory explicitly
    with open(module_path, "w") as f:
        f.write("""
from jawm import Process

p = Process(
    name="yaml_test",
    script="#!/bin/bash\\necho hi",
    logs_directory="from_python",
)

print("LOGDIR=", p.logs_directory)
print("RETRIES=", p.retries)
""")

    # Helper to construct CLI command
    def cli_cmd(args):
        if shutil.which("jawm"):
            return ["jawm", *args]
        return [sys.executable, "-m", "jawm.cli", *args]


    # ------------------------------------------------------------
    # A) NORMAL RUN: Python > YAML
    # ------------------------------------------------------------
    rc1 = subprocess.run(cli_cmd([module_path]), capture_output=True, text=True, timeout=60)
    both1 = (rc1.stdout or "") + (rc1.stderr or "")

    assert rc1.returncode == 0, "❌ Normal run failed"
    assert "from_python" in both1, "❌ Normal run: Python logs_directory should win over YAML"
    assert "RETRIES= 7" not in both1, "❌ Normal run: YAML should not apply without -p"


    # ------------------------------------------------------------
    # B) CLI -p RUN: YAML > Python
    # ------------------------------------------------------------
    rc2 = subprocess.run(cli_cmd([module_path, "-p", yaml_path]), capture_output=True, text=True, timeout=60)
    both2 = (rc2.stdout or "") + (rc2.stderr or "")

    assert rc2.returncode == 0, "❌ CLI -p run failed"
    assert "from_yaml" in both2, "❌ CLI -p: YAML did NOT override Python"
    assert "RETRIES= 7" in both2, "❌ CLI -p: YAML retries not applied"


    # ------------------------------------------------------------
    # C) CLI -l OVERRIDE: CLI > YAML > Python
    # ------------------------------------------------------------
    rc3 = subprocess.run(
        cli_cmd([module_path, "-p", yaml_path, "-l", os.path.join(tmpdir, "forced_logs")]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    both3 = (rc3.stdout or "") + (rc3.stderr or "")

    assert rc3.returncode == 0, "❌ CLI -l run failed"
    assert "LOGDIR= " + os.path.join(tmpdir, "forced_logs") in both3, "❌ CLI -l did NOT override YAML & Python"


    # ------------------------------------------------------------
    # D) CLI -r OVERRIDE: resume flag wins over YAML/Python
    # ------------------------------------------------------------
    rc4 = subprocess.run(
        cli_cmd([module_path, "-p", yaml_path, "-r"]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    both4 = (rc4.stdout or "") + (rc4.stderr or "")

    # resume=True should appear in parameters
    assert "resume" in both4.lower(), "❌ CLI -r: resume flag missing (override not applied)"

    print("✅ Passed: YAML vs Python vs CLI (-l, -r) precedence verified")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)


print("\n>>> Test 44: var precedence — defaults, YAML global/process, Python, CLI-style -p, override")

try:
    # We will test three scenarios in-process (no CLI subprocess):
    #  A) Normal: param_file passed in constructor (Python > YAML)
    #  B) CLI-style: param_file from override_parameters (YAML > Python)
    #  C) CLI-style + override(var): override > YAML > Python

    # ---------- Common setup ----------
    _clear_params()

    tmpdir = tempfile.mkdtemp(prefix="test_precedence_var_", dir=base_tmp)
    yaml_path = os.path.join(tmpdir, "params.yaml")

    # Class defaults (lowest)
    Process.set_default(var={"A": "DEFAULT", "B": "DEFAULT", "C": "DEFAULT"})

    # YAML: one global block + one process block
    with open(yaml_path, "w") as f:
        f.write("""
- scope: global
  var:
    A: "YAML_GLOBAL"
    B: "YAML_GLOBAL"
    C: "YAML_GLOBAL"

- scope: process
  name: "prec_test"
  var:
    B: "YAML_PROCESS"
    C: "YAML_PROCESS"
""")

    # ---------- A) Normal mode: constructor param_file (Python > YAML) ----------
    # default_parameters < YAML(global/process) < kwargs < explicit_args < override_parameters
    _clear_params()
    Process.set_default(var={"A": "DEFAULT", "B": "DEFAULT", "C": "DEFAULT"})

    p_normal = Process(
        name="prec_test",
        script="#!/bin/bash\necho hi",
        var={"A": "PYTHON", "C": "PYTHON"},
        param_file=yaml_path,   # normal: param_file from constructor, not override
    )

    # A: python > YAML_GLOBAL > DEFAULT
    assert p_normal.var["A"] == "PYTHON", (
        f"❌ Normal: var['A'] expected PYTHON, got {p_normal.var['A']}"
    )

    # B: YAML_PROCESS > YAML_GLOBAL > DEFAULT (no python override)
    assert p_normal.var["B"] == "YAML_PROCESS", (
        f"❌ Normal: var['B'] expected YAML_PROCESS, got {p_normal.var['B']}"
    )

    # C: python > YAML_PROCESS > YAML_GLOBAL > DEFAULT in normal mode
    assert p_normal.var["C"] == "PYTHON", (
        f"❌ Normal: var['C'] expected PYTHON, got {p_normal.var['C']}"
    )

    # ---------- B) CLI-style -p: override_parameters.param_file (YAML > Python) ----------
    # default_parameters < kwargs < explicit_args < YAML(global/process) < override_parameters
    _clear_params()
    Process.set_default(var={"A": "DEFAULT", "B": "DEFAULT", "C": "DEFAULT"})
    Process.set_override(param_file=yaml_path)  # simulate CLI -p

    p_cli = Process(
        name="prec_test",
        script="#!/bin/bash\necho hi",
        var={"A": "PYTHON", "C": "PYTHON"},
        # NOTE: no param_file here; picked up from override_parameters
    )

    # A: YAML_GLOBAL (from CLI-style) > PYTHON > DEFAULT
    assert p_cli.var["A"] == "YAML_GLOBAL", (
        f"❌ CLI-style: var['A'] expected YAML_GLOBAL, got {p_cli.var['A']}"
    )

    # B: YAML_PROCESS still wins over YAML_GLOBAL
    assert p_cli.var["B"] == "YAML_PROCESS", (
        f"❌ CLI-style: var['B'] expected YAML_PROCESS, got {p_cli.var['B']}"
    )

    # C: YAML_PROCESS overrides PYTHON in CLI-style mode
    assert p_cli.var["C"] == "YAML_PROCESS", (
        f"❌ CLI-style: var['C'] expected YAML_PROCESS, got {p_cli.var['C']}"
    )

    # ---------- C) CLI-style -p + override(var): override > YAML > Python ----------
    _clear_params()
    Process.set_default(var={"A": "DEFAULT", "B": "DEFAULT", "C": "DEFAULT"})
    Process.set_override(
        param_file=yaml_path,
        var={"A": "OVERRIDE", "B": "OVERRIDE", "C": "OVERRIDE"},
    )

    p_override = Process(
        name="prec_test",
        script="#!/bin/bash\necho hi",
        var={"A": "PYTHON", "C": "PYTHON"},
    )

    assert p_override.var["A"] == "OVERRIDE", (
        f"❌ Override: var['A'] expected OVERRIDE, got {p_override.var['A']}"
    )
    assert p_override.var["B"] == "OVERRIDE", (
        f"❌ Override: var['B'] expected OVERRIDE, got {p_override.var['B']}"
    )
    assert p_override.var["C"] == "OVERRIDE", (
        f"❌ Override: var['C'] expected OVERRIDE, got {p_override.var['C']}"
    )

    print("✅ Passed: var precedence — defaults, YAML global/process, Python, CLI-style -p, override")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    _restore_params(bak_default, bak_override)
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\n>>> Test 45: Process.update — multi-key, override/default, dict/scalar, aliasing, future & existing processes")
try:
    _clear_params()

    # --------------------------
    # Setup temporary dir
    # --------------------------
    tmpdir = tempfile.mkdtemp(prefix="test_update_", dir=base_tmp)

    # --------------------------
    # Setup initial processes
    # --------------------------
    p1 = Process(
        name="p1",
        script="#!/bin/bash\necho hi",
        var={"a": 1, "mk.old": "X"},
        desc="FIRST",
        retries=1,
        logs_directory=os.path.join(tmpdir, "logs_p1")
    )

    p2 = Process(
        name="p2",
        script="#!/bin/bash\necho hi",
        var={"b": 2},
        desc="SECOND",
        retries=2,
        logs_directory=os.path.join(tmpdir, "logs_p2")
    )

    # Mark p2 as executed (should NOT be updated)
    p2.execution_start_at = "20250101_000000"


    # ======================================================
    # A) High-priority override update
    # ======================================================
    Process.update(
        var={"mk.new": "YYY", "c": 300},
        desc="OVERRIDE_DESC",
        retries=99
    )

    # p1 should be updated
    assert p1.var["mk.new"] == "YYY", "❌ override var did not update mk.new on p1"
    assert p1.var["new"] == "YYY", "❌ alias not created for mk.new"
    assert p1.var["c"] == 300, "❌ override dict did not merge key 'c'"
    assert p1.desc == "OVERRIDE_DESC", "❌ override scalar desc not applied"
    assert p1.retries == 99, "❌ override scalar retries not applied"

    # p2 must NOT be updated (executed)
    assert "mk.new" not in p2.var, "❌ executed process var should not update"
    assert p2.desc == "SECOND", "❌ executed process desc updated unexpectedly"

    # ======================================================
    # B) New process inherits override
    # ======================================================
    p3 = Process(
        name="p3",
        script="#!/bin/bash\necho hi",
        var={"x": 10},
        logs_directory=os.path.join(tmpdir, "logs_p3")
    )

    assert p3.var["mk.new"] == "YYY", "❌ future process did not inherit override var"
    assert p3.desc == "OVERRIDE_DESC", "❌ future process did not inherit override desc"
    assert p3.retries == 99, "❌ future process did not inherit override retries"


    # ======================================================
    # C) Default-mode update (override=False)
    # ======================================================
    Process.update(
        override=False,
        var={"d": 400, "c": 999},  # c should NOT overwrite
        desc="DEFAULT_DESC",
        retries=777
    )

    # p1: d should fill, c should NOT replace existing override=300
    assert p1.var["d"] == 400, "❌ default update missing var['d']"
    assert p1.var["c"] == 300, "❌ default update incorrectly overwrote var['c']"

    # desc and retries are already set by override — should NOT be overwritten
    assert p1.desc == "OVERRIDE_DESC", "❌ default update overwrote desc"
    assert p1.retries == 99, "❌ default update overwrote retries"

    # p3: same logic applies
    assert p3.var["d"] == 400, "❌ default update missing var['d'] for p3"
    assert p3.var["c"] == 300, "❌ default update overwrote inherited c on p3"

    # p2 unchanged
    assert "d" not in p2.var, "❌ executed process received default update unexpectedly"


    # ======================================================
    # D) Alias & relpath behavior
    # ======================================================
    Process.update(var={"mk.rel": "./relative/path"})

    assert "mk.rel" in p1.var, "❌ mk.rel missing"
    assert "rel" in p1.var, "❌ alias 'rel' missing for mk.rel"
    assert os.path.isabs(p1.var["mk.rel"]), "❌ mk.rel not expanded to absolute path"
    assert os.path.isabs(p1.var["rel"]), "❌ alias rel not expanded"


    # ======================================================
    # E) params sync maintained
    # ======================================================
    assert p1.params["desc"] == p1.desc, "❌ params.desc mismatch"
    assert p3.params["retries"] == p3.retries, "❌ params.retries mismatch"
    assert p1.params["var"]["mk.new"] == "YYY", "❌ params.var not synced"


    # ======================================================
    # F) Multi-key update works
    # ======================================================
    Process.update(
        var={"z": 999},
        logs_directory=os.path.join(tmpdir, "logs_multi"),
        retries=123
    )

    assert p1.var["z"] == 999, "❌ multi-key update failed (var)"
    assert p1.logs_directory.endswith("logs_multi"), "❌ multi-key update failed (logs_directory)"
    assert p1.retries == 123, "❌ multi-key update failed (retries)"

    # p3 also updated
    assert p3.var["z"] == 999, "❌ multi-key update failed on p3"


    print("✅ Passed: Process.update — fully validated (override/default, var/scalar, alias, future/existing, multi-key)")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)
    # Also clear out Process registry to avoid test interference
    time.sleep(2)
    Process.registry.clear()


print("\n>>> Test 46: CLI nested overrides — global + process pattern matching")

try:
    _clear_params()

    # --- Setup workspace ---
    tmpdir = tempfile.mkdtemp(prefix="test_cli_nested_overrides_", dir=base_tmp)
    module_path = os.path.join(tmpdir, "test_mod.py")

    # Python module creates three Processes:
    #   p1 (should match p* pattern)
    #   p2 (should match p* pattern)
    #   x1 (should NOT match p* pattern)
    with open(module_path, "w") as f:
        f.write(r'''
from jawm import Process

p1 = Process(
    name="p1",
    script="#!/bin/bash\necho hi",
    var={"a": "PY", "b": "PY"},
    manager_slurm={"resources": {"mem": "PY"}},
)

p2 = Process(
    name="p2",
    script="#!/bin/bash\necho hi",
    var={"a": "PY", "b": "PY"},
    manager_slurm={"resources": {"mem": "PY"}},
)

x1 = Process(
    name="x1",
    script="#!/bin/bash\necho hi",
    var={"a": "PY", "b": "PY"},
    manager_slurm={"resources": {"mem": "PY"}},
)

print("P1_VAR=", p1.var)
print("P2_VAR=", p2.var)
print("X1_VAR=", x1.var)

print("P1_SLURM=", p1.manager_slurm)
print("P2_SLURM=", p2.manager_slurm)
print("X1_SLURM=", x1.manager_slurm)
''')

    # Helper: run CLI
    def cli_cmd(args):
        if shutil.which("jawm"):
            return ["jawm", *args]
        return [sys.executable, "-m", "jawm.cli", *args]


    # ============================================================
    # Apply mixed overrides:
    #
    #   --global.var.g=999
    #   --process.p*.var.a=11
    #   --process.p1.var.x=55
    #   --process.p*.manager_slurm.resources.mem=2048
    # ============================================================
    rc = subprocess.run(
        cli_cmd([
            module_path,
            "--global.var.g=999",
            "--process.p*.var.a=11",
            "--process.p1.var.x=55",
            "--process.p*.manager_slurm.resources.mem=2048",
        ]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    out = (rc.stdout or "") + (rc.stderr or "")
    print(out)

    assert rc.returncode == 0, "❌ CLI mixed override execution failed"

    # ------------------------------------------------------------------
    # Validate var merging
    # ------------------------------------------------------------------

    # p1:
    #   PY base + global g=999 + process p* a=11 + process p1 x=55
    assert "P1_VAR= {'a': '11', 'b': 'PY', 'g': '999', 'x': '55'}" in out.replace('"', "'"), \
        "❌ p1.var did not receive combined overrides correctly"

    # p2:
    #   PY base + global g=999 + process p* a=11
    #   (NOT p1.x=55)
    assert "P2_VAR= {'a': '11', 'b': 'PY', 'g': '999'}" in out.replace('"', "'"), \
        "❌ p2.var did not receive correct pattern-matched overrides"

    # x1:
    #   PY base + global g=999 only
    #   (should NOT receive p* overrides)
    assert "X1_VAR= {'a': 'PY', 'b': 'PY', 'g': '999'}" in out.replace('"', "'"), \
        "❌ x1.var incorrectly received process-specific overrides"

    # ------------------------------------------------------------------
    # Validate nested manager_slurm merging
    # ------------------------------------------------------------------

    # p1 & p2 should both receive mem=2048
    assert "'mem': '2048'" in out, "❌ p1/p2 did not receive mem override"

    # x1 should NOT receive mem override
    assert "X1_SLURM=" in out
    assert "{'resources': {'mem': 'PY'}}" in out, \
        "❌ x1 incorrectly received process-specific slurm override"


    # ============================================================
    # EXTRA: Test space-syntax + mk special-case coalescing
    #   --global.var.g 999
    #   --global.var.mk.output_folder mk_out_dir
    #   --process.p*.var.a 11
    #   --process.p1.var.x 55
    # ============================================================
    mk_out_dir = tempfile.mkdtemp(prefix="mk_out_dir_", dir=tmpdir)
    rc2 = subprocess.run(
        cli_cmd([
            module_path,
            "--global.var.g", "999",
            "--global.var.mk.output_folder", mk_out_dir,
            "--process.p*.var.a", "11",
            "--process.p1.var.x", "55",
            "--process.p*.manager_slurm.resources.mem", "2048",
        ]),
        capture_output=True,
        text=True,
        timeout=60,
    )
    out2 = (rc2.stdout or "") + (rc2.stderr or "")
    print(out2)

    assert rc2.returncode == 0, "❌ CLI space-syntax override execution failed"

    # Grab only the var lines so checks are stable even if other logs change
    def _line(prefix, blob):
        for ln in blob.splitlines():
            if ln.startswith(prefix):
                return ln.replace('"', "'")
        return ""

    p1_line = _line("P1_VAR=", out2)
    p2_line = _line("P2_VAR=", out2)
    x1_line = _line("X1_VAR=", out2)

    # Space-syntax worked (same semantic outcome)
    assert "'g': '999'" in p1_line and "'a': '11'" in p1_line and "'x': '55'" in p1_line, \
        f"❌ p1.var missing expected overrides (space syntax). Got: {p1_line}"
    assert "'g': '999'" in p2_line and "'a': '11'" in p2_line and "'x':" not in p2_line, \
        f"❌ p2.var overrides incorrect (space syntax). Got: {p2_line}"
    assert "'g': '999'" in x1_line and "'a': 'PY'" in x1_line, \
        f"❌ x1.var overrides incorrect (space syntax). Got: {x1_line}"

    # mk special-case: should be coalesced into dotted key, NOT nested dict
    
    assert f"'mk.output_folder': '{mk_out_dir}'" in p1_line, f"❌ mk coalescing failed for p1. Got: {p1_line}"
    assert f"'mk.output_folder': '{mk_out_dir}'" in p2_line, f"❌ mk coalescing failed for p2. Got: {p2_line}"
    assert f"'mk.output_folder': '{mk_out_dir}'" in x1_line, f"❌ mk coalescing failed for x1. Got: {x1_line}"

    # Ensure it did NOT become nested {"mk": {...}} in the printed var dict line
    assert "'mk': {" not in p1_line and "'mk': {" not in p2_line and "'mk': {" not in x1_line, \
        "❌ mk was nested instead of being coalesced to mk.output_folder"

    print("✅ Passed: CLI nested overrides — global, process patterns, space syntax and mk special-case")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    shutil.rmtree(mk_out_dir, ignore_errors=True)
    _restore_params(bak_default, bak_override)


print("\n>>> Test 47: get_cls_var — default, YAML(-p), CLI global override, class override (NO -v influence)")

try:
    _clear_params()

    # -----------------------------------------------
    # Setup temporary YAML file for -p
    # -----------------------------------------------
    tmpdir = tempfile.mkdtemp(prefix="test_cls_var_", dir=base_tmp)
    yaml_path = os.path.join(tmpdir, "params.yaml")

    with open(yaml_path, "w") as f:
        f.write("""
- scope: global
  var:
    A: "YAML_GLOBAL"
    B: "YAML_GLOBAL"
    X: "YAML_GLOBAL"
""")

    # -----------------------------------------------
    # A) class defaults only
    # -----------------------------------------------
    Process.set_default(var={"A": "DEFAULT", "B": "DEFAULT", "C": "DEFAULT"})

    v = Process.get_cls_var()
    assert v["A"] == "DEFAULT", "❌ default var not used"
    assert v["B"] == "DEFAULT", "❌ default var not used"
    assert v["C"] == "DEFAULT", "❌ default var not used"

    # -----------------------------------------------
    # B) simulate CLI -p (YAML > default)
    # -----------------------------------------------
    Process.set_override(param_file=yaml_path)

    v = Process.get_cls_var()
    assert v["A"] == "YAML_GLOBAL", "❌ YAML_GLOBAL did not override default"
    assert v["B"] == "YAML_GLOBAL", "❌ YAML_GLOBAL did not override default"
    assert v["X"] == "YAML_GLOBAL", "❌ YAML var missing"

    # -----------------------------------------------
    # C) simulate CLI global override (--global.var.A=CLI)
    # -----------------------------------------------
    Process._cli_global_overrides["var"] = {"A": "CLI"}

    v = Process.get_cls_var()
    assert v["A"] == "CLI", "❌ CLI global override did not override YAML"
    assert v["B"] == "YAML_GLOBAL", "❌ CLI global override incorrectly affected B"

    # -----------------------------------------------
    # D) class override_parameters should override everything
    # -----------------------------------------------
    Process.set_override(var={"B": "OVERRIDE", "C": "OVERRIDE"})

    v = Process.get_cls_var()
    assert v["B"] == "OVERRIDE", "❌ override did not override YAML/default"
    assert v["C"] == "OVERRIDE", "❌ override did not override defaults"

    # -----------------------------------------------
    # E) -v should NOT affect class-level var
    # -----------------------------------------------
    Process.set_override(var_file=yaml_path)  # simulate -v test.yaml

    v = Process.get_cls_var()
    assert "X" in v, "❌ YAML_GLOBAL missing unexpectedly"
    assert v["X"] == "YAML_GLOBAL", "❌ var_file incorrectly affected YAML var"
    assert v["A"] == "CLI", "❌ -v should NOT override CLI or -p"

    # -----------------------------------------------
    # F) instance-level Process.var should stay independent
    # -----------------------------------------------
    p = Process(name="dummy", script="#!/bin/bash\necho hi")

    assert p.var["A"] == "CLI" or p.var["A"] == "YAML_GLOBAL" or p.var["A"] == "DEFAULT", \
        "❌ p.var['A'] invalid — but this is just a sanity check for isolation"

    # A) must not be the same object
    assert Process.get_cls_var() is not p.var, \
        "❌ get_cls_var and p.var reference the same dict object (identity leak)"

    # B) modifying instance var must not affect class-level var
    p.var["__TEST_INSTANCE_MUTATION__"] = 123
    assert "__TEST_INSTANCE_MUTATION__" not in Process.get_cls_var(), \
        "❌ modifying instance var unexpectedly changed class-level var"

    # C) modifying class-level merged var must not affect p.var
    cls_before = Process.get_cls_var().copy()
    Process.set_default(var={"__TEST_CLASS_MUTATION__": 456})
    cls_after = Process.get_cls_var()
    assert "__TEST_CLASS_MUTATION__" in cls_after, "❌ class-level mutation missing"
    assert "__TEST_CLASS_MUTATION__" not in p.var, \
        "❌ modifying class-level var unexpectedly changed instance var"

    print("✅ Passed: get_cls_var — correct precedence and correct -v behavior")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)
    Process._cli_global_overrides["var"] = {}   # cleanup


print("\n>>> Test 48: Process.wait skip logic — non-executed vs dependency-blocked processes")
tmpdir = tempfile.mkdtemp(prefix="test_wait_skip_", dir=base_tmp)
try:
    _clear_params()

    logs_dir = os.path.join(tmpdir, "logs")

    # --------------------------------------------------
    # A) Process created but never executed (no deps)
    # --------------------------------------------------
    p1 = Process(
        name="never_started",
        script="#!/bin/bash\necho hi",
        logs_directory=logs_dir
    )

    # Should NOT hang
    # Should return True
    # Should NOT mark wait as failed
    result = Process.wait(p1.hash)
    assert result is True, "❌ wait() should return True when skipping an unstarted standalone process"

    # Process never ran → exitcode must be None
    assert p1.get_exitcode() is None, "❌ get_exitcode() should be None for never-started process"

    # --------------------------------------------------
    # B) Dependency-blocked process must NOT be skipped
    # --------------------------------------------------
    marker = os.path.join(tmpdir, "marker.txt")

    m = Process(
        name="dep_map",
        script=f"""#!/bin/bash
sleep 1
echo OK > "{marker}"
""",
        logs_directory=logs_dir
    )

    f = Process(
        name="dep_flag",
        script=f"""#!/bin/bash
if [ ! -f "{marker}" ]; then
  echo "MARKER_MISSING"
  exit 2
fi
echo OK
""",
        logs_directory=logs_dir
    )

    # Execute only the mapping process
    m.execute()

    # dep_flag has depends_on but has NOT started yet → must NOT be skipped
    result = Process.wait([m.hash, f.hash])
    assert result is True, "❌ wait() should not fail for dependency-blocked processes"

    # Now execute the dependent process
    f.execute(depends_on=m.hash)

    # Wait for dependent process to finish
    result = Process.wait(f.hash)
    assert result is True, "❌ wait() failed for dependent process"
    assert f.get_exitcode().startswith("0"), "❌ dependent process failed unexpectedly"

    print("✅ Passed: Process.wait skip logic (non-executed vs dependency-blocked)")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)


print("\n>>> Test 49: User config loading — default path, custom path, env precedence")
try:
    # --------------------------------------------------
    # Backup environment (FULL isolation)
    # --------------------------------------------------
    _env_backup = dict(os.environ)

    # --------------------------------------------------
    # Setup isolated HOME
    # --------------------------------------------------
    tmp_home = tempfile.mkdtemp(prefix="jawm_home_", dir=base_tmp)
    os.environ["HOME"] = tmp_home

    jawm_dir = os.path.join(tmp_home, ".jawm")
    os.makedirs(jawm_dir, exist_ok=True)

    default_cfg = os.path.join(jawm_dir, "config")

    # --------------------------------------------------
    # Write default ~/.jawm/config
    # --------------------------------------------------
    with open(default_cfg, "w") as f:
        f.write("""
# Default config
JAWM_MAX_PROCESS=10
JAWM_PROCESS_WAIT_POLL=0.5
NOT_JAWM_VAR=SHOULD_IGNORE
""")

    # Remove any inherited JAWM_* vars
    for k in list(os.environ):
        if k.startswith("JAWM_"):
            del os.environ[k]

    # --------------------------------------------------
    # Load config (default path)
    # --------------------------------------------------
    from jawm._config import _load_user_config
    _load_user_config()

    assert os.environ.get("JAWM_MAX_PROCESS") == "10", \
        "❌ Failed to load JAWM_MAX_PROCESS from default config"

    assert os.environ.get("JAWM_PROCESS_WAIT_POLL") == "0.5", \
        "❌ Failed to load JAWM_PROCESS_WAIT_POLL from default config"

    assert "NOT_JAWM_VAR" not in os.environ, \
        "❌ Non-JAWM variable was incorrectly loaded"

    # --------------------------------------------------
    # Custom config via JAWM_CONFIG_FILE
    # --------------------------------------------------
    custom_cfg = os.path.join(tmp_home, "custom.conf")
    with open(custom_cfg, "w") as f:
        f.write("""
JAWM_MAX_PROCESS=20
JAWM_LOG_EMOJI=0
""")

    os.environ["JAWM_CONFIG_FILE"] = custom_cfg

    # Clear JAWM_* except JAWM_CONFIG_FILE
    for k in list(os.environ):
        if k.startswith("JAWM_") and k != "JAWM_CONFIG_FILE":
            del os.environ[k]

    _load_user_config()

    assert os.environ.get("JAWM_MAX_PROCESS") == "20", \
        "❌ Failed to load JAWM_MAX_PROCESS from custom config"

    assert os.environ.get("JAWM_LOG_EMOJI") == "0", \
        "❌ Failed to load JAWM_LOG_EMOJI from custom config"

    # --------------------------------------------------
    # Env vars must override config
    # --------------------------------------------------
    os.environ["JAWM_MAX_PROCESS"] = "99"
    _load_user_config()

    assert os.environ.get("JAWM_MAX_PROCESS") == "99", \
        "❌ Config incorrectly overrode explicit env var"

    print("✅ Passed: user config loading — default path, custom path, env precedence")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    # --------------------------------------------------
    # Cleanup filesystem & restore environment
    # --------------------------------------------------
    shutil.rmtree(tmp_home, ignore_errors=True)

    os.environ.clear()
    os.environ.update(_env_backup)


print("\n>>> Test 50: CLI remote -p/-v URL (HTML blob -> retry ?raw=1 -> success + cache)")
try:
    _clear_params()

    # Workspace
    tmpdir = tempfile.mkdtemp(prefix="test_cli_remote_url_", dir=base_tmp)
    cache_dir = os.path.join(tmpdir, "remote_params")
    os.makedirs(cache_dir, exist_ok=True)

    out_json = os.path.join(tmpdir, "out.json")
    module_path = os.path.join(tmpdir, "test_mod_remote.py")

    # Module executed by cli.main() – writes observed values to JSON for assertions
    with open(module_path, "w") as f:
        f.write(r'''
from jawm import Process
import os, json

p1 = Process(name="p1", script="#!/bin/bash\necho hi")

out = os.environ["JAWM_TEST_OUT"]
data = {
  "p1_var": p1.var,
  "REMOTE_VAR_YAML": globals().get("REMOTE_VAR_YAML"),
  "REMOTE_NUMBER": globals().get("REMOTE_NUMBER"),
  "REMOTE_FLAG": globals().get("REMOTE_FLAG"),
}
with open(out, "w") as fh:
  json.dump(data, fh)
''')

    # Simulated user-provided "blob" URLs (these return HTML first)
    blob_params_url = "https://github.com/mpg-age-bioinformatics/jawm_git_test/blob/main/params/params.yaml"
    blob_vars_url   = "https://github.com/mpg-age-bioinformatics/jawm_git_test/blob/main/params/vars.yaml"

    # Remote YAML content returned on retry (?raw=1)
    params_yaml = (
        b"- scope: global\n"
        b"  desc: \"desc_from_remote_params\"\n"
        b"  var:\n"
        b"    REMOTE_PARAM_YAML: \"ok-from-remote-params\"\n"
        b"\n"
        b"- scope: process\n"
        b"  name: \"*\"\n"
        b"  var:\n"
        b"    REMOTE_PARAM_APPLIES_TO_ALL: \"yes\"\n"
    )

    vars_yaml = (
        b"REMOTE_VAR_YAML: \"ok-from-remote-vars\"\n"
        b"REMOTE_NUMBER: 123\n"
        b"REMOTE_FLAG: true\n"
    )

    html_blob = b"<!doctype html><html><body>blob page</body></html>"

    # Mock urlopen
    import urllib.request
    old_urlopen = urllib.request.urlopen

    class _Resp:
        def __init__(self, data, url):
            self._data = data
            self._url = url
        def __enter__(self): return self
        def __exit__(self, exc_type, exc, tb): return False
        def geturl(self): return self._url
        def read(self, n=-1):
            if n is None or n < 0:
                return self._data
            return self._data[:n]

    calls = {"n": 0}
    def _mock_urlopen(req, timeout=None):
        calls["n"] += 1
        u = getattr(req, "full_url", str(req))

        # params
        if u.startswith(blob_params_url):
            if "raw=1" in u:
                return _Resp(params_yaml, u)
            return _Resp(html_blob, u)

        # vars
        if u.startswith(blob_vars_url):
            if "raw=1" in u:
                return _Resp(vars_yaml, u)
            return _Resp(html_blob, u)

        raise RuntimeError("Unexpected URL in test: " + u)

    # Run CLI in-process
    import jawm.cli as cli
    old_argv = sys.argv[:]
    old_env = os.environ.copy()

    try:
        urllib.request.urlopen = _mock_urlopen

        os.environ["JAWM_ALLOW_URL_CONFIG"] = "1"
        os.environ["JAWM_URL_CACHE_DIR"] = cache_dir
        os.environ["JAWM_URL_MAX_BYTES"] = str(1024 * 1024)
        os.environ["JAWM_URL_FORCE_REFRESH"] = "1"
        os.environ["JAWM_TEST_OUT"] = out_json

        sys.argv = ["jawm", module_path, "-p", blob_params_url, "-v", blob_vars_url]
        cli.main()

        with open(out_json, "r") as fh:
            data = json.load(fh)

        # Validate -p merged into Process.var
        assert data["p1_var"].get("REMOTE_PARAM_YAML") == "ok-from-remote-params", "❌ -p remote params not applied"
        assert data["p1_var"].get("REMOTE_PARAM_APPLIES_TO_ALL") == "yes", "❌ -p process/global merge not applied"

        # Validate -v injected globals into module namespace
        assert data["REMOTE_VAR_YAML"] == "ok-from-remote-vars", "❌ -v remote vars not injected"
        assert data["REMOTE_NUMBER"] == 123, "❌ -v REMOTE_NUMBER mismatch"
        assert data["REMOTE_FLAG"] is True, "❌ -v REMOTE_FLAG mismatch"

        # Validate cache: second run should not call urlopen if force refresh off
        os.environ["JAWM_URL_FORCE_REFRESH"] = "0"
        urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("urlopen called despite cache"))

        cli.main()

    finally:
        urllib.request.urlopen = old_urlopen
        sys.argv = old_argv
        os.environ.clear()
        os.environ.update(old_env)

    print("✅ Passed: CLI remote -p/-v URL (HTML retry + cache)")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)
    try:
        Process.registry.clear()
    except Exception:
        pass


print("\n>>> Test 51: CLI -w/--workdir creates + chdir early (relative -l resolves under workdir)")

tmpdir = None
try:
    def run_cli(args, timeout=45, cwd=None):
        r = subprocess.run(cli_cmd(args), capture_output=True, text=True, timeout=timeout, cwd=cwd)
        both = (r.stdout or "") + (r.stderr or "")
        return r.returncode, r.stdout, r.stderr, both

    def cli_cmd(args):
        if shutil.which("jawm"):
            return ["jawm", *args]
        return [sys.executable, "-m", "jawm.cli", *args]
        _clear_params()

    tmpdir = tempfile.mkdtemp(prefix="test_cli_workdir_", dir=base_tmp)

    # Create a minimal workflow directory (absolute path)
    wf_dir = os.path.join(tmpdir, "workflow_abs")
    os.makedirs(wf_dir, exist_ok=True)
    with open(os.path.join(wf_dir, "main.py"), "w", encoding="utf-8") as f:
        f.write("print('WORKDIR_TEST_RUN')\n")

    # Workdir does NOT exist yet (CLI should create it)
    workdir = os.path.join(tmpdir, "new_workdir")
    assert not os.path.exists(workdir), "❌ precondition failed: workdir should not exist yet"

    # Use a RELATIVE logs directory on purpose; should resolve under -w after os.chdir()
    rel_logs = "logs_rel"
    expected_runs_dir = os.path.join(workdir, rel_logs, "jawm_runs")

    # Run from a different cwd to ensure we don't accidentally create logs in the caller cwd
    rc, out, err, both = run_cli([wf_dir, "-w", workdir, "-l", rel_logs], cwd=tmpdir)
    print(both)
    assert rc == 0, f"❌ CLI failed with -w\n{both}"
    assert "WORKDIR_TEST_RUN" in both, "❌ workflow did not run (missing expected stdout marker)"

    # Workdir should be created
    assert os.path.isdir(workdir), "❌ -w did not create the workdir"

    # Logs should be created under workdir (because -w applied early)
    assert os.path.isdir(expected_runs_dir), (
        f"❌ expected logs directory not created under workdir: {expected_runs_dir}"
    )
    log_files = glob(os.path.join(expected_runs_dir, "*.log"))
    assert log_files, "❌ No CLI run log file created under workdir logs directory"

    # And NOT created in the original cwd (tmpdir)
    assert not os.path.isdir(os.path.join(tmpdir, rel_logs)), (
        "❌ logs_rel unexpectedly created in the caller cwd; -w may not be applied early"
    )

    # ------------------------------------------------------------
    # Negative test: -w points to an existing file => exit code 2
    # ------------------------------------------------------------
    bad_path = os.path.join(tmpdir, "not_a_dir")
    with open(bad_path, "w", encoding="utf-8") as f:
        f.write("I am a file, not a directory.\n")

    rc2, out2, err2, both2 = run_cli([wf_dir, "-w", bad_path], cwd=tmpdir)
    print(both2)
    assert rc2 == 2, f"❌ expected rc=2 when -w points to a file, got rc={rc2}\n{both2}"

    print("✅ Passed: CLI -w/--workdir creates directory + applies cwd early + rejects file target")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    try:
        if tmpdir and os.path.isdir(tmpdir):
            shutil.rmtree(tmpdir, ignore_errors=True)
        _restore_params(bak_default, bak_override)
        Process.registry.clear()
    except Exception:
        pass


print("\n>>> Test 52: Python cli.run wrapper (subprocess/inprocess, argv string, cwd, check)")
try:
    import jawm.cli as jawm_cli

    tmpdir = tempfile.mkdtemp(prefix="test_py_cli_run_", dir=base_tmp)
    workdir = os.path.join(tmpdir, "work")
    os.makedirs(workdir, exist_ok=True)

    # Create a minimal script that the CLI can execute (direct .py path)
    script_path = os.path.join(workdir, "script.py")
    with open(script_path, "w") as f:
        f.write("print('PY_CLI_RUN_OK')\n")

    # ---- 1) Default mode (subprocess) with list argv + capture ----
    logs1 = "logs_1"
    rc, out, err = jawm_cli.run(["script.py", "-l", logs1], cwd=workdir, capture=True)
    assert rc == 0, f"❌ cli.run subprocess(list) failed rc={rc}\nstdout:\n{out}\nstderr:\n{err}"
    assert "PY_CLI_RUN_OK" in (out + err), "❌ subprocess capture did not include script output"
    assert os.path.isdir(os.path.join(workdir, logs1, "jawm_runs")), "❌ logs_1/jawm_runs not created under cwd"

    # ---- 2) Subprocess with string argv (shlex.split) ----
    logs2 = "logs_2"
    rc, out, err = jawm_cli.run(f"script.py -l {logs2}", cwd=workdir, capture=True)
    assert rc == 0, f"❌ cli.run subprocess(str) failed rc={rc}\nstdout:\n{out}\nstderr:\n{err}"
    assert "PY_CLI_RUN_OK" in (out + err), "❌ subprocess(str) capture did not include script output"
    assert os.path.isdir(os.path.join(workdir, logs2, "jawm_runs")), "❌ logs_2/jawm_runs not created under cwd"

    # ---- 3) In-process run (no subprocess) ----
    logs3 = "logs_3"
    rc = jawm_cli.run(["script.py", "-l", logs3], cwd=workdir, inprocess=True)
    assert rc == 0, f"❌ cli.run inprocess(list) failed rc={rc}"
    assert os.path.isdir(os.path.join(workdir, logs3, "jawm_runs")), "❌ logs_3/jawm_runs not created under cwd (inprocess)"

    # ---- 4) check=True should raise on failure ----
    raised = False
    try:
        # Intentionally missing script
        jawm_cli.run(["definitely_not_here_12345.py"], cwd=workdir, check=True, capture=True)
    except RuntimeError:
        raised = True
    assert raised, "❌ check=True did not raise RuntimeError on failure"

    print("✅ Passed: Python cli.run wrapper (subprocess/inprocess, argv string, cwd, check)")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


print("\n>>> Test 53: YAML includes (list-of-entries) — YAML-file-relative + wildcard + ../path + precedence at position")

try:
    _clear_params()

    # --- Setup workspace ---
    tmpdir = tempfile.mkdtemp(prefix="test_yaml_includes_", dir=base_tmp)
    module_path = os.path.join(tmpdir, "test_mod_includes.py")

    # Put main.yaml in a subfolder so includes MUST be YAML-relative (not CWD-relative)
    cfg_dir = os.path.join(tmpdir, "cfg")
    os.makedirs(cfg_dir, exist_ok=True)

    # An include directory with multiple YAMLs (for wildcard tests)
    inc_dir = os.path.join(tmpdir, "inc")
    os.makedirs(inc_dir, exist_ok=True)

    # Included YAML (base.yaml) at tmpdir/base.yaml (included via ../base.yaml)
    base_yaml = os.path.join(tmpdir, "base.yaml")
    with open(base_yaml, "w") as f:
        f.write(
            """\
- scope: global
  var:
    x: "BASE"
    z: "BASEZ"

- scope: process
  name: "p*"
  var:
    a: "BASEA"
"""
        )

    # Two wildcard-included YAMLs in tmpdir/inc/*.yaml
    # These are included AFTER "MAINZ_BEFORE" but BEFORE "MAINX_AFTER"
    # so they must override earlier entries but be overridable by later entries.
    inc1_yaml = os.path.join(inc_dir, "10_inc.yaml")
    with open(inc1_yaml, "w") as f:
        f.write(
            """\
- scope: global
  var:
    w: "W1"
    z: "Z_FROM_WILDCARD_1"
"""
        )

    inc2_yaml = os.path.join(inc_dir, "20_inc.yaml")
    with open(inc2_yaml, "w") as f:
        f.write(
            """\
- scope: global
  var:
    w2: "W2"
    z: "Z_FROM_WILDCARD_2"
"""
        )

    # Main YAML includes:
    #  - "../base.yaml"               (../path include)
    #  - "../inc/*.yaml"              (wildcard include, two files)
    #  - "../no_such_dir/*.yaml"      (wildcard matches nothing; should NOT error)
    # Order matters for precedence.
    main_yaml = os.path.join(cfg_dir, "main.yaml")
    with open(main_yaml, "w") as f:
        f.write(
            """\
- scope: global
  var:
    z: "MAINZ_BEFORE"

- includes:
  - "../base.yaml"
  - "../inc/*.yaml"
  - "../no_such_dir/*.yaml"

- scope: global
  var:
    x: "MAINX_AFTER"

- scope: process
  name: "p1"
  var:
    a: "MAIN_P1"
"""
        )

    # Module prints final resolved vars
    with open(module_path, "w") as f:
        f.write(
            r'''
from jawm import Process

p1 = Process(
    name="p1",
    script="#!/bin/bash\necho hi",
    var={"local": "L"},
)

x1 = Process(
    name="x1",
    script="#!/bin/bash\necho hi",
    var={"local": "L"},
)

print("P1_VAR=", p1.var)
print("X1_VAR=", x1.var)
'''
        )

    def cli_cmd(args):
        if shutil.which("jawm"):
            return ["jawm", *args]
        return [sys.executable, "-m", "jawm.cli", *args]

    # IMPORTANT:
    # Run from a cwd that is NOT cfg_dir (and not tmpdir), to prove YAML-relative includes work.
    rc = subprocess.run(
        cli_cmd([module_path, "-p", main_yaml]),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=base_tmp,
    )

    out = (rc.stdout or "") + (rc.stderr or "")
    print(out)
    assert rc.returncode == 0, "❌ CLI run with includes failed"

    outq = out.replace('"', "'")
    assert "P1_VAR=" in outq and "X1_VAR=" in outq, "❌ Missing var output lines"

    # --- Expected precedence checks (include spliced at position) ---
    #
    # z:
    #   MAINZ_BEFORE (before includes)
    #   then base.yaml sets z=BASEZ
    #   then wildcard inc/*.yaml sets z=Z_FROM_WILDCARD_2 (because 20_inc.yaml > 10_inc.yaml in sorted order)
    # so final z must be Z_FROM_WILDCARD_2
    #
    # x:
    #   base.yaml sets x=BASE
    #   then after includes main.yaml sets x=MAINX_AFTER
    #
    # p1 a:
    #   base.yaml process p* sets a=BASEA
    #   main.yaml later sets p1 a=MAIN_P1
    #
    # wildcard vars:
    #   w=W1, w2=W2 should exist
    assert "'local': 'L'" in outq, "❌ local key missing"
    assert "'x': 'MAINX_AFTER'" in outq, "❌ x precedence failed (should be MAINX_AFTER)"
    assert "'z': 'Z_FROM_WILDCARD_2'" in outq, "❌ z precedence failed (should come from wildcard include)"
    assert "'w': 'W1'" in outq and "'w2': 'W2'" in outq, "❌ wildcard-included globals missing"
    assert "P1_VAR=" in outq and "'a': 'MAIN_P1'" in outq, "❌ p1 process override failed (a should be MAIN_P1)"

    # x1 should get globals x/z/w/w2 but not process 'a'
    x1_line = ""
    for ln in outq.splitlines():
        if ln.startswith("X1_VAR="):
            x1_line = ln
            break
    assert x1_line, "❌ Could not find X1_VAR line"
    assert "'x': 'MAINX_AFTER'" in x1_line and "'z': 'Z_FROM_WILDCARD_2'" in x1_line, "❌ x1 did not receive global vars"
    assert "'w': 'W1'" in x1_line and "'w2': 'W2'" in x1_line, "❌ x1 missing wildcard globals"
    assert "'a':" not in x1_line, "❌ x1 incorrectly received process var 'a' from p*"

    print("✅ Passed: YAML includes — YAML-relative, wildcard, ../path, spliced order, precedence")
    passed += 1

except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
    _restore_params(bak_default, bak_override)




# -----------------------------
# Cleanup created directories
# -----------------------------
for d in [
    "logs_test", "logs_test_default", "logs_from_yaml_global", "logs_from_yaml_process",
    "logs_test_hash", "logs_resume_test", "logs_default_override", "logs_override_test",
    "logs_test_update_vars", "logs_test_tail_concurrent", "logs_test_parallel", "data_test",
    "logs", "logs_ar", "logs_allow_skip", "logs_test_auto_mount", "logs_test_clone_hash",
    "logs_temp", "logs_cli_sanitize", "logs_nbdeps", "logs_norm", "logs_pfalse",
    "logs_sync_test", "logs_test_alias", "cli_out_dir"
]:
    if d == "logs":
        if os.path.isdir("logs"):
            for sub in os.listdir("logs"):
                subpath = os.path.join("logs", sub)
                if sub.startswith("jawm_has"):
                    continue
                shutil.rmtree(subpath, ignore_errors=True) if os.path.isdir(subpath) else os.remove(subpath)
    else:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------
# Summary of the test cases
# ---------------------------

print("\n===== TEST SUMMARY =====")
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")

if failed == 0:
    print("🎉 All tests passed!")
else:
    print("⚠️ Some tests failed — review the output.")

sys.exit(failed)