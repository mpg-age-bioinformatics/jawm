import os
import time
import sys
import subprocess
from jawm import Process

passed = 0
failed = 0

Process.reset_stop()

print(">>> Test 1: Basic Inline Script Execution")
time.sleep(0.5)
try:
    proc1 = Process(
        name="basic_hello",
        script="""#!/bin/bash
    echo 'Hello JAWM!'
    """,
        logs_directory="logs_test"
    )
    proc1.execute()
    Process.wait(proc1.hash)
    assert proc1.get_exitcode() == "0", "❌ Basic execution failed"
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
        script="""#!/bin/bash
    echo 'Step B done'
    """,
        depends_on=["step_a"],
        logs_directory="logs_test"
    )
    proc2a.execute()
    proc2b.execute()
    Process.wait(["step_a", "step_b"])
    assert proc2a.get_exitcode() == "0", "❌ step_a failed"
    assert proc2b.get_exitcode() == "0", "❌ step_b failed"
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
    assert proc3.get_exitcode() != "0", "❌ Retry test unexpectedly succeeded"
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
        script="""#!/bin/bash
    echo "Job name is {{APPNAME}}"
    """,
        script_variables={"APPNAME": "JAWM-Test"},
        logs_directory="logs_test"
    )
    proc6.execute()
    Process.wait(proc6.hash)
    out6 = proc6.get_output()
    assert "JAWM-Test" in out6, "❌ script_variables not substituted correctly"
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
        script_variables_file="data_test/vars.rc",
        logs_directory="logs_test"
    )
    proc7.execute()
    Process.wait(proc7.hash)
    out7 = proc7.get_output()
    assert "Hello from file" in out7, "❌ script_variables_file substitution failed"
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

    assert proc11.params.get("retries") == 5, "❌ Process-specific value not applied"
    assert "logs_from_yaml_process" in proc11.logs_directory, "❌ logs_directory not from process scope"
    print("✅ Passed: YAML Parameter Resolution")
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
        script_variables={"MESSAGE": "Hello"},
        validation="strict"
    )
    assert proc12g.is_valid("strict"), "❌ Placeholder defined but still failed strict validation"


    print("✅ Passed: Validation Logic (Basic & Strict Modes)")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1

Process.reset_stop()


print("\n>>> Test 13: JAWM CLI Integration (workflow execution, -p, -v, fallback, error handling)")
time.sleep(0.5)

try:
    # --- Setup test_scripts directory ---
    os.makedirs("test_scripts", exist_ok=True)

    # 1. Basic script execution with -v
    with open("test_scripts/main.py", "w") as f:
        f.write("""#!/usr/bin/env python3
print("HELLO_FROM_CLI")
""")
    with open("test_scripts/test_vars.yaml", "w") as f:
        f.write("GREETING: 'Hello from variables'")

    result1 = subprocess.run(
        ["jawm", "test_scripts", "-v", "test_scripts"],
        capture_output=True,
        text=True,
        timeout=10
    )
    assert result1.returncode == 0, "❌ CLI exited with non-zero status (basic -v)"
    assert "HELLO_FROM_CLI" in result1.stdout, "❌ Output missing (basic -v)"
    assert "Injected 1 variable" in result1.stdout or result1.stderr, "❌ Variable injection not logged"

    # 2. Script execution with -p
    with open("test_scripts/test_params.yaml", "w") as f:
        f.write("""
- scope: global
  logs_directory: test_logs_from_params
""")
    result2 = subprocess.run(
        ["jawm", "test_scripts", "-p", "test_scripts/test_params.yaml"],
        capture_output=True,
        text=True,
        timeout=10
    )
    assert result2.returncode == 0, "❌ CLI exited with non-zero status (-p)"
    assert "test_params.yaml" in result2.stdout or result2.stderr, "❌ Parameter file usage not logged"

    # 3. Fallback to current directory (no workflow argument)
    os.makedirs("test_scripts_current", exist_ok=True)
    with open("test_scripts_current/main.py", "w") as f:
        f.write("""#!/usr/bin/env python3
print("DEFAULT_DIR_TEST")
""")
    current_dir = os.getcwd()
    os.chdir("test_scripts_current")
    result3 = subprocess.run(
        ["jawm"],
        capture_output=True,
        text=True,
        timeout=10
    )
    os.chdir(current_dir)
    assert result3.returncode == 0, "❌ CLI failed to execute from default dir"
    assert "DEFAULT_DIR_TEST" in result3.stdout, "❌ Default dir script output missing"

    # 4. Invalid directory should fail cleanly
    result4 = subprocess.run(
        ["jawm", "non_existing_folder_123"],
        capture_output=True,
        text=True,
        timeout=10
    )
    assert result4.returncode != 0, "❌ CLI should fail on invalid path"
    assert "Invalid workflow path" in result4.stderr or result4.stdout, "❌ Missing error message on invalid path"

    print("✅ Passed: CLI invocation, variable injection, param loading, fallback, and error handling")
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
        manager="local",
        logs_directory="logs_test_hash"
    )

    proc14b = Process(
        name="hash_test",
        script="#!/bin/bash\necho Hello",
        manager="local",
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
        manager="local",
        resume=True
    )
    proc15a.execute()
    Process.wait(proc15a.hash)

    assert proc15a.get_exitcode() == "0", "❌ First run did not finish successfully"

    # Step 2: Clone the process
    proc15b = proc15a.copy()
    proc15b.execute()

    Process.wait(proc15b.hash)

    # Step 3: Confirm resume behavior
    assert proc15b.log_path == proc15a.log_path, "❌ Resume did not use existing log folder"
    assert proc15b.get_exitcode() == "0", "❌ Resume did not resolve to a successful result"
    assert proc15b.finished_event.is_set(), "❌ Resume process did not mark itself as finished"
    assert proc15b.execution_end_at is not None, "❌ Resume process was not marked as completed"

    print(f"✅ Passed: Resume correctly skipped execution and reused logs from {os.path.basename(proc15b.log_path)}")
    passed += 1
except Exception as e:
    print(f"❌ Failed: {e}")
    failed += 1



print("\n===== TEST SUMMARY =====")
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")

if failed == 0:
    print("🎉 All tests passed!")
else:
    print("⚠️ Some tests failed — review the output.")

sys.exit(failed)