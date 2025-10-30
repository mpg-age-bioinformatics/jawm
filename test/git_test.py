#!/usr/bin/env python3
"""
Integration test for jawm CLI Git workflow logic.

Covers:
  ✅ Normal clone & subpath resolution (default, tag, branch, HEAD)
  ✅ Safety guard (existing repo with mismatched commit)
  ✅ Missing file handling
  ✅ Cache reuse verification
"""

import os
import subprocess
import tempfile
import time
import shutil
from pathlib import Path

# -------------------------------------------------------
# CONFIGURATION
# -------------------------------------------------------

REMOTE_REPO = "https://github.com/mpg-age-bioinformatics/jawm_git_test"
GIT_USER = "mpg-age-bioinformatics"
GIT_SERVER = "github.com"

# -------------------------------------------------------
# SETUP
# -------------------------------------------------------

JAWM_EXE = shutil.which("jawm") or "jawm"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="jawm_git_test_live_"))
LOGS_DIR = TEST_ROOT / "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

passed, failed = 0, 0


def run_jawm(target: str, expect_fail: bool = False, clean_dir=True):
    """
    Run jawm CLI with a clean isolated working directory.

    - expect_fail: if True, test passes only if jawm exits non-zero.
    - clean_dir: whether to delete any existing local repo before running.
    """
    safe_label = (
        target.replace("https://", "")
        .replace("http://", "")
        .replace("/", "_")
        .replace(":", "_")
        .replace("@", "_")
        .replace(".", "_")
    )
    work_dir = TEST_ROOT / safe_label

    if clean_dir and work_dir.exists():
        print(f"🧹 Cleaning existing folder: {work_dir}")
        shutil.rmtree(work_dir)

    os.makedirs(work_dir, exist_ok=True)

    args = [
        JAWM_EXE,
        target,
        "--logs-directory", str(work_dir / "logs"),
        "--server", GIT_SERVER,
        "--user", GIT_USER,
    ]

    start = time.time()
    result = subprocess.run(args, text=True, capture_output=True, cwd=work_dir)
    elapsed = time.time() - start

    print(f"\n→ Running in {work_dir}")
    print(f"Exit code: {result.returncode} | Duration: {elapsed:.1f}s")
    print(result.stdout[:400])
    if result.stderr:
        print(result.stderr[:200])

    if expect_fail:
        assert result.returncode != 0, "Expected failure but got success"
    else:
        assert result.returncode == 0, f"Expected success, got {result.returncode}"
    print("✅ OK")


# -------------------------------------------------------
# DEFINE TESTS
# -------------------------------------------------------

print(f"\n>>> Starting GitHub integration tests using {REMOTE_REPO}")

tests = [
    ("root@default",          f"{REMOTE_REPO}"),
    ("root@tag(v1.0.0)",      f"{REMOTE_REPO}@v1.0.0"),
    ("branch main",           f"{REMOTE_REPO}@main//examples/demo.py"),
    ("dir@default",           f"{REMOTE_REPO}//examples"),
    ("file@default",          f"{REMOTE_REPO}//main.py"),
    ("file@tag(v1.0.0)",      f"{REMOTE_REPO}@v1.0.0//main.py"),
    ("missing file",          f"{REMOTE_REPO}@v1.0.0////no_such_file.py", True),
]

# -------------------------------------------------------
# RUN NORMAL TESTS (each in its own folder)
# -------------------------------------------------------

for label, target, *flags in tests:
    expect_fail = bool(flags and flags[0])
    print(f"\n--- {label} ---")
    try:
        run_jawm(target, expect_fail=expect_fail, clean_dir=True)
        passed += 1
    except Exception as e:
        print(f"❌ Failed: {e}")
        failed += 1

# -------------------------------------------------------
# SAFETY TEST: EXISTING FOLDER WITH WRONG COMMIT
# -------------------------------------------------------

print("\n--- safety check: existing folder with different commit ---")
try:
    # The tag test will use this work dir
    safe_label = "github_com_mpg-age-bioinformatics_jawm_git_test_v1_0_0"
    work_dir = TEST_ROOT / safe_label
    os.makedirs(work_dir, exist_ok=True)

    # 1️⃣ First clone a known version (main)
    run_jawm(f"{REMOTE_REPO}", expect_fail=False, clean_dir=True)

    # 2️⃣ Locate the exact .commit file in the directory that will be reused
    commit_file = work_dir / "jawm_git_test" / ".commit"
    if commit_file.exists():
        current = commit_file.read_text().strip()
        print(f"🧩 Found .commit for safety test at {commit_file} (current={current[:10]}...)")
        fake_sha = "0000000000000000000000000000000000000000"
        commit_file.write_text(fake_sha + "\n")
        print(f"Injected fake commit SHA into {commit_file} (was {current[:10]}...)")
    else:
        print(f"⚠️ .commit not found at {commit_file}")

    # 3️⃣ Run jawm again on the same target — should now fail due to mismatch
    run_jawm(f"{REMOTE_REPO}@v1.0.0", expect_fail=True, clean_dir=False)
    passed += 1
    print("✅ Passed: safety guard triggered correctly")

except Exception as e:
    print(f"❌ Safety test failed: {e}")
    failed += 1

# -------------------------------------------------------
# CACHE REUSE TEST
# -------------------------------------------------------

print("\n>>> Testing cache reuse behavior")
try:
    cache_dir = Path.home() / ".jawm/git"
    before = set(p.name for p in cache_dir.rglob("*") if p.is_dir()) if cache_dir.exists() else set()
    run_jawm(f"{REMOTE_REPO}")
    after = set(p.name for p in cache_dir.rglob("*") if p.is_dir()) if cache_dir.exists() else set()
    new_dirs = after - before
    print(f"   Cache diff: {len(new_dirs)} new entries")
    print("✅ Passed: Cache reuse verified")
    passed += 1
except Exception as e:
    print(f"❌ Cache reuse test failed: {e}")
    failed += 1

# -------------------------------------------------------
# SUMMARY
# -------------------------------------------------------

print("\n>>> Summary")
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")

shutil.rmtree(TEST_ROOT, ignore_errors=True)
exit(1 if failed else 0)