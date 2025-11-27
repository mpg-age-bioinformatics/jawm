import os
import time
import sys
import subprocess
import shutil
import tempfile
import re
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


print("\n>>> Test 20: Parallelism True vs False (timing + overlap checks)")
# time.sleep(0.5)
try:
    def parse_epochs(text):
        """
        Extract integer epochs from lines like: 'EPOCH LABEL N'
        Returns a list of ints; ignores lines that don't match.
        """
        epochs = []
        if not text:
            return epochs
        for line in text.splitlines():
            m = re.match(r"^\s*(\d{9,})\s+[A-D]\s+\d+\s*$", line.strip())
            if m:
                try:
                    epochs.append(int(m.group(1)))
                except Exception:
                    pass
        return sorted(epochs)

    # Common 3-iteration script that prints epoch seconds + label + counter
    def loop_script(label):
        return f"""#!/bin/bash
for i in {{1..3}}; do
    echo "$(date +%s) {label} $i"
    sleep 1
done
"""

    logs_dir = "logs_test_parallel"

    # --------------- A) parallel=True (default): should overlap ---------------
    pA = Process(
        name="parallel_true_A",
        script=loop_script("A"),
        logs_directory=logs_dir
    )
    pB = Process(
        name="parallel_true_B",
        script=loop_script("B"),
        logs_directory=logs_dir
    )

    t0 = time.time()
    pA.execute()
    pB.execute()
    Process.wait([pA.hash, pB.hash])
    t1 = time.time()
    elapsed_parallel = t1 - t0

    outA = pA.get_output()
    outB = pB.get_output()
    A_epochs = parse_epochs(outA)
    B_epochs = parse_epochs(outB)

    assert pA.get_exitcode().startswith("0"), "❌ parallel=True: A exit code non-zero"
    assert pB.get_exitcode().startswith("0"), "❌ parallel=True: B exit code non-zero"
    assert len(A_epochs) >= 3 and len(B_epochs) >= 3, "❌ parallel=True: missing epoch lines"

    # Ranges overlap check: [minA, maxA] intersects [minB, maxB]
    overlap_parallel = (min(A_epochs) <= max(B_epochs)) and (min(B_epochs) <= max(A_epochs))
    assert overlap_parallel, "❌ parallel=True: expected overlapping execution windows"

    # --------------- B) parallel=False: must run one-after-another ---------------
    pC = Process(
        name="parallel_false_A",
        script=loop_script("C"),
        logs_directory=logs_dir,
        parallel=False
    )
    pD = Process(
        name="parallel_false_B",
        script=loop_script("D"),
        logs_directory=logs_dir,
        parallel=False
    )

    t2 = time.time()
    pC.execute()
    pD.execute()
    Process.wait([pC.hash, pD.hash])
    t3 = time.time()
    elapsed_serial = t3 - t2

    outC = pC.get_output()
    outD = pD.get_output()
    C_epochs = parse_epochs(outC)
    D_epochs = parse_epochs(outD)

    assert pC.get_exitcode().startswith("0"), "❌ parallel=False: C exit code non-zero"
    assert pD.get_exitcode().startswith("0"), "❌ parallel=False: D exit code non-zero"
    assert len(C_epochs) >= 3 and len(D_epochs) >= 3, "❌ parallel=False: missing epoch lines"

    # Non-overlap check: earliest D is strictly after latest C
    no_overlap_serial = min(D_epochs) > max(C_epochs)
    assert no_overlap_serial, (
        "❌ parallel=False: detected overlap — D started before C fully finished"
    )

    # --------------- Timing sanity checks (robust to system variance) ---------------
    # Each script loops ~3 seconds; parallel should be clearly faster than serial.
    assert elapsed_serial >= 5.0, f"❌ Serial run unusually fast: {elapsed_serial:.1f}s"
    assert elapsed_parallel < (elapsed_serial * 0.75), (
        f"❌ Expected parallel run at least 25% faster: parallel={elapsed_parallel:.1f}s, serial={elapsed_serial:.1f}s"
    )
    # Optional soft cap to catch extreme slowness on overloaded machines:
    # assert elapsed_parallel < 8.0, f"❌ Parallel took unusually long: {elapsed_parallel:.1f}s"

    print(
        f"✅ Passed: Parallelism True vs False "
        f"(parallel={elapsed_parallel:.1f}s, serial={elapsed_serial:.1f}s; "
        f"overlap=True, serialized=True)"
    )
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

try:
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