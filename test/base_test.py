import os
import time
import sys
import subprocess
import shutil
import tempfile
import re
from glob import glob
from jawm import Process, utils

passed = 0
failed = 0

Process.reset_stop()

print(">>> Test 1: Basic Inline Script Execution")
time.sleep(0.5)
try:
    proc1 = Process(
        name="basic_hello",
        script="""#!/usr/bin/env python3
print('Hello JAWM!')
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
time.sleep(0.5)
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
time.sleep(0.5)
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
    time.sleep(0.5)
    print("✅ Passed: Retry Mechanism")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1

# Clear any global state
Process.reset_stop()


print("\n>>> Test 4: Output, Error, and Command Log Check")
time.sleep(0.5)
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
time.sleep(0.5)
try:
    all_procs = Process.list_all()
    assert all(p["finished"] for p in all_procs), "❌ Some processes not marked finished"
    print(f"✅ Passed: {len(all_procs)} Process(es) tracked and marked finished")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 6: Script Variable Substitution")
time.sleep(0.5)
try:
    proc6 = Process(
        name="var_subst",
        script="""#!/usr/bin/env python3
print("Job name is {{APPNAME}}")
""",
        var={"APPNAME": "JAWM-Test"},
        logs_directory="logs_test"
    )
    proc6.execute()
    Process.wait(proc6.hash)
    out6 = proc6.get_output()
    assert "JAWM-Test" in out6, "❌ var not substituted correctly"
    print("✅ Passed: Script Variable Substitution")
    passed += 1
except Exception as e:
    print(f"❌ Failed: — {e}")
    failed += 1


print("\n>>> Test 7: Script Variable File Substitution")
time.sleep(0.5)

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
time.sleep(0.5)
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


print("\n>>> Test 9: Process Cloning with `copy()`")
time.sleep(0.5)
try:
    original = Process(
        name="original_proc",
        script="""#!/bin/bash
echo 'Original'
""",
        logs_directory="logs_test"
    )
    clone = original.copy(name="cloned_proc", script="""#!/bin/bash
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
time.sleep(0.5)
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
time.sleep(0.5)
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
time.sleep(0.5)
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


print("\n>>> Test 13: JAWM CLI Integration ")
time.sleep(0.5)

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
    with tempfile.TemporaryDirectory(prefix="cli_it_") as root:

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
            f.write("print('RUN_JAWM')\n")
        rc, out, err, both = run_cli([g_dir])
        assert rc == 0 and "RUN_JAWM" in both and "RUN_MAIN" not in both, "❌ Did not prefer jawm.py over main.py"

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
time.sleep(0.5)
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
time.sleep(0.5)
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
    proc15b = proc15a.copy()
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
time.sleep(0.5)
try:
    # Clear any defaults/overrides first
    Process.default_parameters.clear()
    Process.override_parameters.clear()

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
    Process.override_parameters.clear()
    Process.default_parameters.clear()


print("\n>>> Test 17: update_vars() supports list of files and YAML directory")
time.sleep(0.5)
try:

    # ---------- A) List of files ----------
    tmpA = tempfile.mkdtemp(prefix="update_vars_list_")
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
    tmpB = tempfile.mkdtemp(prefix="update_vars_dir_")
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
time.sleep(0.5)
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
time.sleep(0.5)
try:
    # --- Setup a temp directory with inputs ---
    tmpdir = tempfile.mkdtemp(prefix="hash_inputs_")
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
time.sleep(0.5)
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
    assert dn.get_exitcode() == "0", "❌ always_run should run despite global stop"
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
time.sleep(0.5)
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
    assert dnA.get_exitcode() == "0", "❌ Default should allow skipped dependency"
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
time.sleep(0.5)
try:
    # prepare a simple directory and input file
    tmp_dir = tempfile.mkdtemp(prefix="auto_mount_test_")
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
        print("   Skipped (no container backend available)")

    print("✅ Passed: Auto mk./map. vars mount")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1


# print("\n>>> Test 24: CLI --hash <yaml> minimal flow (new → mismatch → overwrite)")

# def cli_cmd(args):
#     if shutil.which("jawm"):
#         return ["jawm", *args]
#     return [sys.executable, "-m", "jawm.cli", *args]

# def run_cli(args, timeout=45, cwd=None):
#     r = subprocess.run(cli_cmd(args), capture_output=True, text=True, timeout=timeout, cwd=cwd)
#     return r.returncode, r.stdout, r.stderr, (r.stdout or "") + (r.stderr or "")

# root = tempfile.mkdtemp(prefix="cli_hash_yaml_")
# try:
#     wf = os.path.join(root, "wf")
#     os.makedirs(wf, exist_ok=True)

#     # Workflow that writes a predictable output file under logs_yamlhash/
#     main_py = os.path.join(wf, "main.py")
#     with open(main_py, "w", encoding="utf-8") as f:
#         f.write("""from jawm import Process
# p = Process(
#     name="demo_yaml_hash",
#     script='''#!/bin/bash
# echo "RUN_ID=run1"
# ''',
#     logs_directory="logs_yamlhash"
# )
# p.execute()
# Process.wait(p.hash)
# """)

#     # YAML: hash the workflow + all produced .output files
#     yaml_path = os.path.join(wf, "hash.yaml")
#     with open(yaml_path, "w", encoding="utf-8") as f:
#         f.write("""include:
#   - main.py
#   - logs_yamlhash/**/*.output
# allowed_extensions: [py, output]
# exclude_dirs: [__pycache__, jawm_runs, jawm_hashes]
# exclude_files: ["*.tmp", "*.swp"]
# recursive: true
# """)

#     # Place CLI logs (and the baseline hash file) under wf/logs
#     cli_logs_dir = os.path.join(wf, "logs")
#     hash_dir  = os.path.join(cli_logs_dir, "jawm_hashes")
#     hash_file = os.path.join(hash_dir, "main.hash")

#     # 1) First run → baseline created
#     rc, _, _, both = run_cli([".", "--hash", "hash.yaml", "-l", "logs"], cwd=wf)
#     assert rc == 0, f"❌ CLI failed on first YAML hash run:\n{both}"
#     assert os.path.isfile(hash_file), "❌ main.hash missing after first run"
#     with open(hash_file, "r", encoding="utf-8") as f: h1 = f.read().strip()
#     assert re.fullmatch(r"[0-9a-fA-F]{64}", h1), f"❌ hash not hex: {h1}"

#     # 2) Change workflow output → expect mismatch (baseline not overwritten)
#     with open(main_py, "r+", encoding="utf-8") as f:
#         txt = f.read().replace("run1", "run2")
#         f.seek(0); f.write(txt); f.truncate()

#     rc, _, _, both = run_cli([".", "--hash", "hash.yaml", "-l", "logs"], cwd=wf)
#     assert rc == 0, f"❌ CLI failed after change:\n{both}"
#     with open(hash_file, "r", encoding="utf-8") as f: h2 = f.read().strip()
#     assert h2 == h1, "❌ baseline should NOT be overwritten by default on mismatch"

#     # 3) Add overwrite:true → baseline MUST update
#     with open(yaml_path, "a", encoding="utf-8") as f:
#         f.write("overwrite: true\n")

#     rc, _, _, both = run_cli([".", "--hash", "hash.yaml", "-l", "logs"], cwd=wf)
#     assert rc == 0, f"❌ CLI failed on overwrite run:\n{both}"
#     with open(hash_file, "r", encoding="utf-8") as f: h3 = f.read().strip()
#     assert h3 != h1, "❌ baseline not updated with overwrite:true"

#     print("✅ Passed: CLI --hash <yaml> minimal flow (new → mismatch → overwrite)")
#     passed += 1
# except Exception as e:
#     print(f"❌ Failed: {e}")
#     failed += 1
# finally:
#     shutil.rmtree(root, ignore_errors=True)


print("\n>>> Test 25: update_params invalidates cached script (var re-substitution)")
try:
    # workspace
    tmpdir = tempfile.mkdtemp(prefix="upd_params_")
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



# -----------------------------
# Cleanup created directories
# -----------------------------
for d in [
    "logs_test", "logs_test_default", "logs_from_yaml_global", "logs_from_yaml_process",
    "logs_test_hash", "logs_resume_test", "logs_default_override", "logs_override_test",
    "logs_test_update_vars", "logs_test_tail_concurrent", "logs_test_parallel", "data_test",
    "logs", "logs_ar", "logs_allow_skip", "logs_test_auto_mount"
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