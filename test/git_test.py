#!/usr/bin/env python3
import os, sys, subprocess, tempfile, pathlib, shutil, time, re

def sh(args, **kw):
    kw.setdefault("text", True)
    kw.setdefault("capture_output", True)
    return subprocess.run(args, **kw)

def cli_cmd():
    return ["jawm"] if shutil.which("jawm") else [sys.executable, "-m", "jawm.cli"]

def run_jawm(target, logs_dir, env):
    cmd = cli_cmd() + [target, "-l", str(logs_dir)]
    return sh(cmd, env=env)

def make_local_bare_repo():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="jawm_git_offline_"))
    work = tmp / "work"
    bare = tmp / "origin.git"
    work.mkdir()

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    # init work repo
    assert sh(["git", "init"], cwd=work, env=env).returncode == 0
    sh(["git", "config", "user.name", "Test"], cwd=work, env=env)
    sh(["git", "config", "user.email", "test@example.com"], cwd=work, env=env)

    # commit 1: jawm.py
    (work / "jawm.py").write_text("print('ROOT jawm.py v1')\n", encoding="utf-8")
    assert sh(["git", "add", "."], cwd=work, env=env).returncode == 0
    assert sh(["git", "commit", "-m", "c1 root jawm"], cwd=work, env=env).returncode == 0
    assert sh(["git", "tag", "v1.0.0"], cwd=work, env=env).returncode == 0

    # commit 2: examples/demo/jawm.py
    (work / "examples").mkdir(exist_ok=True)
    (work / "examples" / "demo").mkdir(exist_ok=True)
    (work / "examples" / "demo" / "jawm.py").write_text("print('DEMO jawm.py')\n", encoding="utf-8")
    assert sh(["git", "add", "."], cwd=work, env=env).returncode == 0
    assert sh(["git", "commit", "-m", "c2 demo jawm"], cwd=work, env=env).returncode == 0

    # commit 3: test.py
    (work / "test.py").write_text("print('TEST file ran')\n", encoding="utf-8")
    assert sh(["git", "add", "."], cwd=work, env=env).returncode == 0
    assert sh(["git", "commit", "-m", "c3 add test.py"], cwd=work, env=env).returncode == 0

    # branch: feature modifies test.py
    assert sh(["git", "checkout", "-b", "feature/branch"], cwd=work, env=env).returncode == 0
    (work / "test.py").write_text("print('TEST file on feature branch')\n", encoding="utf-8")
    assert sh(["git", "commit", "-am", "c4 feature change"], cwd=work, env=env).returncode == 0

    # back to default branch (main)
    # create main if not exists, then point HEAD to it
    sh(["git", "checkout", "-B", "main"], cwd=work, env=env)

    # record shas
    sha_head = sh(["git", "rev-parse", "HEAD"], cwd=work, env=env).stdout.strip()
    sha_c2 = sh(["git", "rev-parse", "HEAD~1"], cwd=work, env=env).stdout.strip()  # commit 2
    sha_c1 = sh(["git", "rev-parse", "HEAD~2"], cwd=work, env=env).stdout.strip()  # commit 1

    # make bare
    assert sh(["git", "clone", "--bare", str(work), str(bare)], env=env).returncode == 0
    # set HEAD -> refs/heads/main
    (bare / "HEAD").write_text("ref: refs/heads/main\n")

    return tmp, bare, {"HEAD": sha_head, "C2": sha_c2, "C1": sha_c1}

def parse_resolved_path(output):
    m = re.search(r"resolved '.*?'\s*→\s*'([^']+)'", output)
    return m.group(1) if m else None

def main():
    tmp, bare, shas = make_local_bare_repo()

    cache = tmp / "cache"
    logs = tmp / "logs"
    cache.mkdir(); logs.mkdir()

    env = os.environ.copy()
    env["JAWM_GIT_CACHE"] = str(cache)
    env["GIT_TERMINAL_PROMPT"] = "0"   # never prompt
    # file:// URL to the bare repo
    file_repo = "file://" + str(bare)

    tests = [
        ("root@default",          f"{file_repo}"),
        ("root@tag(v1.0.0)",      f"{file_repo}@v1.0.0"),
        ("root@sha(HEAD)",        f"{file_repo}@{shas['HEAD']}"),
        ("dir@default",           f"{file_repo}//examples/demo"),
        ("dir@sha(C2)",           f"{file_repo}@{shas['C2']}//examples/demo"),
        ("file@default",          f"{file_repo}//test.py"),
        ("file@sha(HEAD)",        f"{file_repo}@{shas['HEAD']}//test.py"),
        ("file@sha(C1) (missing)",f"{file_repo}@{shas['C1']}//test.py", True),  # should fail: file not yet added
        ("branch feature/file",   f"{file_repo}@feature/branch//test.py"),
        ("cache_hit_repeat_root", f"{file_repo}"),
    ]

    passed = failed = skipped = 0

    print(f"Repo (bare): {bare}")
    print(f"HEAD: {shas['HEAD'][:12]}  C2: {shas['C2'][:12]}  C1: {shas['C1'][:12]}\n")

    for name, target, *maybe_neg in tests:
        expect_fail = bool(maybe_neg[0]) if maybe_neg else False
        t0 = time.time()
        p = run_jawm(target, logs, env)
        dt = time.time() - t0
        if expect_fail:
            if p.returncode != 0:
                print(f"✅ {name}: expected failure (rc={p.returncode}) in {dt:.2f}s")
                passed += 1
            else:
                print(f"❌ {name}: expected non-zero rc, got 0")
                failed += 1
            continue

        if p.returncode == 0:
            resolved = parse_resolved_path((p.stdout or "") + (p.stderr or ""))
            print(f"✅ {name}: rc=0 in {dt:.2f}s  {('→ ' + resolved) if resolved else ''}")
            passed += 1
        else:
            print(f"❌ {name}: rc={p.returncode}")
            print((p.stdout or "")[-800:])
            print((p.stderr or "")[-800:])
            failed += 1

    print("\n=== SUMMARY ===")
    print(f"Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
    # cleanup temp tree
    shutil.rmtree(tmp, ignore_errors=True)
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
