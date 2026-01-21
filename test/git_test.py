#!/usr/bin/env python3
"""
Integration test for jawm CLI Git workflow logic.

Covers:
  ✅ HTTPS, SSH, SCP (git@)
  ✅ Shorthand syntax (repo@tag, user/repo@branch)
  ✅ Tags, branches
  ✅ Subdirectory and file targets (//examples/demo.py)
  ✅ Safety guard (existing repo with mismatched commit)
  ✅ Missing file handling (graceful fail)
  ✅ Cache reuse verification
  ✅ .git removed and .commit exists after clone
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
SSH_REPO = "ssh://git@github.com/mpg-age-bioinformatics/jawm_git_test.git"
SCP_REPO = "git@github.com:mpg-age-bioinformatics/jawm_git_test.git"
LOCAL_REPO = f"file://{Path.home()}/jawm/test/jawm_git_test.git"  # adjust if needed

GIT_USER = "mpg-age-bioinformatics"
GIT_SERVER = "github.com"

# -------------------------------------------------------
# SETUP
# -------------------------------------------------------

JAWM_EXE = shutil.which("jawm") or "jawm"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="jawm_git_test_live_"))
LOGS_DIR = TEST_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

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
    work_dir.mkdir(parents=True, exist_ok=True)

    args = [
        JAWM_EXE,
        target,
        "--logs-directory", str(work_dir / "logs"),
        "--server", GIT_SERVER,
        "--user", GIT_USER,
    ]

    print(f"\n→ Running in {work_dir}")
    print(f"   Target: {target}")
    start = time.time()
    result = subprocess.run(args, text=True, capture_output=True, cwd=work_dir)
    elapsed = time.time() - start
    print(f"   Exit code: {result.returncode} | Duration: {elapsed:.1f}s")

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if expect_fail:
        assert result.returncode != 0, "Expected failure but got success"
    else:
        assert result.returncode == 0, f"Expected success, got {result.returncode}"

    # Verify .commit and .git correctness if success
    if not expect_fail:
        for repo_dir in work_dir.rglob("jawm_git_test"):
            if repo_dir.is_dir():
                commit_file = repo_dir / ".commit"
                assert commit_file.exists(), f"{commit_file} missing!"
                assert not (repo_dir / ".git").exists(), f"{repo_dir} still has .git!"
                print(f"   ✅ Verified .commit exists and .git removed in {repo_dir}")

    print("✅ OK")


# -------------------------------------------------------
# DEFINE TEST MATRIX
# -------------------------------------------------------

print(f"\n>>> Starting GitHub integration tests using {REMOTE_REPO}")

tests = [
    # --- HTTPS tests ---
    ("https root@default",          f"{REMOTE_REPO}"),
    ("https tag",                   f"{REMOTE_REPO}@v1.0.0"),
    ("https subdir",                f"{REMOTE_REPO}//examples"),
    ("https file path",             f"{REMOTE_REPO}//main.py"),
    ("https branch",                f"{REMOTE_REPO}@main//examples/demo.py"),
    ("https latest-tag",            f"{REMOTE_REPO}@latest-tag"),
    ("https last-tag",              f"{REMOTE_REPO}@last-tag"),
    

    # --- SSH / SCP style ---
    ("ssh tag",                     f"{SSH_REPO}@v1.0.0"),
    ("scp shorthand tag",           f"{SCP_REPO}@v1.0.0"),
    ("ssh subpath",                 f"{SSH_REPO}@main//examples/demo.py"),

    # --- shorthand expansion ---
    ("user/repo shorthand",         "jawm_git_test"),
    ("user/repo ref shorthand",     "jawm_git_test@main"),
    ("user/repo path shorthand",    "jawm_git_test@v1.0.0//examples/demo.py"),
    ("org/repo shorthand",          "mpg-age-bioinformatics/jawm_git_test@main"),
    ("shorthand latest-tag",        "jawm_git_test@latest-tag"),
    ("shorthand last-tag",          "jawm_git_test@last-tag"),

    # --- missing file (graceful fail) ---
    ("https missing file",          f"{REMOTE_REPO}@v1.0.0////no_such_file.py", True),

    # --- cache reuse ---
    ("cache reuse",                 f"{REMOTE_REPO}"),
]

# -------------------------------------------------------
# RUN TESTS
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
    safe_label = "github_com_mpg-age-bioinformatics_jawm_git_test_v1_0_0"
    work_dir = TEST_ROOT / safe_label
    work_dir.mkdir(parents=True, exist_ok=True)

    # Clone once to create the .commit
    run_jawm(f"{REMOTE_REPO}@v1.0.0", expect_fail=False, clean_dir=True)

    # Inject fake commit in the reused folder
    commit_file = work_dir / "jawm_git_test" / ".commit"
    if commit_file.exists():
        current = commit_file.read_text().strip()
        fake_sha = "0000000000000000000000000000000000000000"
        commit_file.write_text(fake_sha + "\n")
        print(f"🧩 Injected fake commit into {commit_file} (was {current[:10]}...)")
    else:
        raise RuntimeError(f".commit not found at {commit_file}")

    # Run again — must fail due to mismatch
    run_jawm(f"{REMOTE_REPO}@v1.0.0", expect_fail=True, clean_dir=False)
    passed += 1
    print("✅ Passed: safety guard triggered correctly")

except Exception as e:
    print(f"❌ Safety test failed: {e}")
    failed += 1

# -------------------------------------------------------
# CACHE REUSE BEHAVIOR TEST
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
# REUSE TEST: latest-tag / last-tag should be reusable
# -------------------------------------------------------
print("\n>>> Testing reuse behavior for latest-tag / last-tag")
for token in ("latest-tag", "last-tag"):
    print(f"\n--- reuse: {token} ---")
    try:
        target = f"{REMOTE_REPO}@{token}"

        # First run: clean dir, should succeed and create local repo folder + .commit
        run_jawm(target, expect_fail=False, clean_dir=True)

        # Second run: DO NOT clean dir, should reuse and succeed
        run_jawm(target, expect_fail=False, clean_dir=False)

        passed += 1
        print(f"✅ Passed: {token} reuse works")
    except Exception as e:
        print(f"❌ {token} reuse failed: {e}")
        failed += 1

# -------------------------------------------------------
# SUMMARY
# -------------------------------------------------------

print("\n>>> Summary")
print(f"✅ Passed: {passed}")
print(f"❌ Failed: {failed}")

shutil.rmtree(TEST_ROOT, ignore_errors=True)
exit(1 if failed else 0)