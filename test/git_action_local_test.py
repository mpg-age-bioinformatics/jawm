import os
import time
import sys
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


print("\n===== TEST SUMMARY =====")
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")

if failed == 0:
    print("🎉 All tests passed!")
else:
    print("⚠️ Some tests failed — review the output.")

sys.exit(failed)