import argparse
import subprocess
import sys
import shutil
import urllib.request
import zipfile
import io
from pathlib import Path
from importlib import resources


# ----------------------------------------------------------
#   Version detection (module scope)
# ----------------------------------------------------------

try:
    from importlib import metadata as md  # py>=3.8
except Exception:
    import importlib_metadata as md

_PKG_NAME = (__package__ or "jawm").split(".")[0]

try:
    _VERSION = md.version(_PKG_NAME)
except md.PackageNotFoundError:
    _VERSION = "dev" 


# ----------------------------------------------------------
#  Helper var and methods for jawm-dev command
# ----------------------------------------------------------

_VALID_CMDS = {"init"}

_TEMPLATE_ZIP = "https://github.com/mpg-age-bioinformatics/jawm_demo/archive/refs/heads/main.zip"


def _run_init(module_name, server="github.com", user="mpg-age-bioinformatics", module_prefix="jawm_"):
    """
    Initialize a new jawm workflow project.

    Arguments:
      module_name   – base name used inside Python module (file will be: {module_name}.py)
      server        – 'github.com', 'gitlab.com', 'gitea.example.org', SSH/URL forms, or 'local'
      user          – git username / org / group (used for remote)
      module_prefix – directory/repo name prefix (default: 'jawm_')

    Behavior:
      - Builds repo_name = f"{module_prefix}{module_name}"
      - Always uses SSH remotes: git@<host>:<user>/<repo>.git
      - If server == 'local': no remote is added/created.
      - Else:
          * If remote exists -> exit 1.
          * If remote does not exist:
              - GitHub: auto-create PRIVATE EMPTY repo (gh CLI or REST via GITHUB_TOKEN/GH_TOKEN).
              - GitLab: auto-create PRIVATE EMPTY project in <user> namespace (GITLAB_TOKEN).
              - Gitea : auto-create PRIVATE EMPTY repo in org/user (GITEA_TOKEN).
              - Other  : no auto-create (proceed locally).
      - After git init & remote add, attempts: git push -u origin main (skipped for server == 'local').
    """
    import sys, io, zipfile, shutil, subprocess, os, json, re, urllib.request, urllib.error
    from urllib.parse import urlparse, quote as urlquote
    from pathlib import Path

    # -------------------------
    # Derived names/paths/hosts
    # -------------------------
    repo_name = f"{module_prefix}{module_name}"
    target = Path(repo_name).resolve()

    def _norm_host(s: str) -> str:
        s = (s or "").strip()
        if s.startswith("git@"):
            return s.split("@", 1)[1].split(":", 1)[0].lower()
        if "://" in s:
            try:
                return (urlparse(s).hostname or s).lower()
            except Exception:
                return s.lower()
        return s.lower()

    def _ssh_remote(srv: str, owner: str, repo: str) -> str | None:
        if srv == "local":
            return None
        host = _norm_host(srv).strip("/")
        return f"git@{host}:{owner}/{repo}.git"

    host = _norm_host(server)
    remote_url = _ssh_remote(server, user, repo_name)

    # -------------------------
    # Helpers
    # -------------------------
    def _gh_installed() -> bool:
        try:
            subprocess.run(["gh", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return True
        except Exception:
            return False

    def _git_ls_remote(url: str) -> bool:
        """Returns True if remote appears to exist/accessibly respond (SSH). Private repos may still return non-zero."""
        try:
            env = os.environ.copy()
            env["GIT_ASKPASS"] = "echo"
            env["GIT_SSH_COMMAND"] = env.get("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
            proc = subprocess.run(["git", "ls-remote", "--exit-code", url],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=False)
            return proc.returncode == 0
        except FileNotFoundError:
            return False

    # ---------- GitHub ----------
    def _github_repo_exists(owner: str, name: str) -> bool:
        if _gh_installed():
            proc = subprocess.run(["gh", "repo", "view", f"{owner}/{name}"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return proc.returncode == 0
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if not token:
            # unauth check works only for public repos
            try:
                with urllib.request.urlopen(f"https://github.com/{owner}/{name}") as resp:
                    return resp.status == 200
            except Exception:
                return False
        req = urllib.request.Request(
            f"https://api.github.com/repos/{owner}/{name}",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            return e.code != 404
        except Exception:
            return False

    def _github_create_repo(owner: str, name: str) -> bool:
        # Prefer GitHub CLI: creates empty, private repo (no README)
        if _gh_installed():
            proc = subprocess.run(
                ["gh", "repo", "create", f"{owner}/{name}", "--private", "--confirm"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            return proc.returncode == 0
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if not token:
            print("⚠️  GitHub repo creation skipped: set GITHUB_TOKEN (or GH_TOKEN) or install gh.")
            return False
        headers = {"Authorization": f"Bearer {token}",
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "Content-Type": "application/json"}
        payload = json.dumps({"name": name, "private": True, "auto_init": False}).encode("utf-8")
        # Try org endpoint
        try:
            req = urllib.request.Request(f"https://api.github.com/orgs/{owner}/repos",
                                         data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                return 201 <= resp.status < 300
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404, 422):
                return False
        # Fallback to user endpoint
        try:
            req = urllib.request.Request("https://api.github.com/user/repos",
                                         data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                return 201 <= resp.status < 300
        except Exception:
            return False

    # ---------- GitLab ----------
    def _gitlab_api_base(hostname: str) -> str:
        return f"https://{hostname}/api/v4"

    def _gitlab_namespace_id(hostname: str, namespace: str, token: str) -> int | None:
        base = _gitlab_api_base(hostname)
        req = urllib.request.Request(
            f"{base}/namespaces?search={urlquote(namespace)}",
            headers={"Private-Token": token}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for ns in data:
                    if ns.get("full_path") == namespace or ns.get("path") == namespace:
                        return ns.get("id")
                return data[0]["id"] if data else None
        except Exception:
            return None

    def _gitlab_repo_exists(hostname: str, owner: str, name: str, token: str | None) -> bool:
        base = _gitlab_api_base(hostname)
        path = urlquote(f"{owner}/{name}", safe="")
        headers = {"Private-Token": token} if token else {}
        req = urllib.request.Request(f"{base}/projects/{path}", headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as e:
            return e.code != 404
        except Exception:
            return False

    def _gitlab_create_repo(hostname: str, owner: str, name: str) -> bool:
        token = os.getenv("GITLAB_TOKEN")
        if not token:
            print("⚠️  GitLab repo creation skipped: set GITLAB_TOKEN.")
            return False
        base = _gitlab_api_base(hostname)
        ns_id = _gitlab_namespace_id(hostname, owner, token)
        payload = {"name": name, "path": name, "visibility": "private"}
        if ns_id:
            payload["namespace_id"] = ns_id
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{base}/projects", data=data,
                                     headers={"Private-Token": token, "Content-Type": "application/json"},
                                     method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return 201 <= resp.status < 300
        except Exception:
            return False

    # ---------- Gitea ----------
    def _gitea_api_base(hostname: str) -> str:
        return f"https://{hostname}/api/v1"

    def _gitea_repo_exists(hostname: str, owner: str, name: str, token: str | None) -> bool:
        base = _gitea_api_base(hostname)
        headers = {"Authorization": f"token {token}"} if token else {}
        req = urllib.request.Request(f"{base}/repos/{owner}/{name}", headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as e:
            return e.code != 404
        except Exception:
            return False

    def _gitea_create_repo(hostname: str, owner: str, name: str) -> bool:
        token = os.getenv("GITEA_TOKEN")
        if not token:
            print("⚠️  Gitea repo creation skipped: set GITEA_TOKEN.")
            return False
        base = _gitea_api_base(hostname)
        headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
        payload = json.dumps({"name": name, "private": True, "auto_init": False}).encode("utf-8")
        # Try org endpoint first
        try:
            req = urllib.request.Request(f"{base}/orgs/{owner}/repos", data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                return 201 <= resp.status < 300
        except urllib.error.HTTPError as e:
            if e.code not in (403, 404, 422):
                return False
        # Fallback to user endpoint
        try:
            req = urllib.request.Request(f"{base}/user/repos", data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req) as resp:
                return 201 <= resp.status < 300
        except Exception:
            return False

    # -------------------------
    # REMOTE: check/create (BEFORE scaffolding)
    # -------------------------
    if server != "local":
        if host == "github.com":
            if _github_repo_exists(user, repo_name):
                print(f"❌ Remote already exists on GitHub: git@github.com:{user}/{repo_name}.git")
                sys.exit(1)
            print(f"🛠️  Creating GitHub repository {user}/{repo_name} (private, empty)…")
            if not _github_create_repo(user, repo_name):
                print("❌ Failed to create remote repository on GitHub. Aborting.")
                sys.exit(1)
            print("✅ Remote repository created on GitHub.")
        elif "gitlab" in host:
            token = os.getenv("GITLAB_TOKEN")
            if _gitlab_repo_exists(host, user, repo_name, token):
                print(f"❌ Remote already exists on GitLab: git@{host}:{user}/{repo_name}.git")
                sys.exit(1)
            print(f"🛠️  Creating GitLab project {user}/{repo_name} (private, empty)…")
            if not _gitlab_create_repo(host, user, repo_name):
                print("❌ Failed to create project on GitLab. Aborting.")
                sys.exit(1)
            print("✅ Remote project created on GitLab.")
        elif "gitea" in host:
            token = os.getenv("GITEA_TOKEN")
            if _gitea_repo_exists(host, user, repo_name, token):
                print(f"❌ Remote already exists on Gitea: git@{host}:{user}/{repo_name}.git")
                sys.exit(1)
            print(f"🛠️  Creating Gitea repository {user}/{repo_name} (private, empty)…")
            if not _gitea_create_repo(host, user, repo_name):
                print("❌ Failed to create repository on Gitea. Aborting.")
                sys.exit(1)
            print("✅ Remote repository created on Gitea.")
        else:
            if remote_url and _git_ls_remote(remote_url):
                print(f"❌ Remote already exists: {remote_url}")
                sys.exit(1)

    # -------------------------
    # LOCAL SCAFFOLD
    # -------------------------
    if target.exists():
        print(f"❌ Directory already exists: {target}")
        sys.exit(1)

    print(f"🧩 Creating new jawm workflow project: {repo_name}")
    print(f"→ Downloading template ZIP from {_TEMPLATE_ZIP}")

    try:
        with urllib.request.urlopen(_TEMPLATE_ZIP) as resp:
            with zipfile.ZipFile(io.BytesIO(resp.read())) as zf:
                root_dir = zf.namelist()[0].split("/")[0]
                temp_extract = target.parent / root_dir
                zf.extractall(target.parent)
        shutil.move(str(temp_extract), str(target))
    except Exception as e:
        print(f"❌ Failed to download or extract template: {e}")
        sys.exit(1)

    # Remove leftover git metadata/ignore
    # for item in [".gitignore"]:
    #     p = target / item
    #     if p.exists():
    #         (shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink())

    # Rename demo.py → {module_name}.py
    template_py = target / "demo.py"
    module_py = target / f"{module_name}.py"
    if template_py.exists():
        try:
            template_py.rename(module_py)
            print(f"📄 Renamed demo.py → {module_name}.py")
        except Exception as e:
            print(f"⚠️ Failed to rename demo.py: {e}")

    # --- Rename submodule directory and file ---
    submods_dir = target / "submodules"
    old_subdir = submods_dir / "jawm_demo_submodule"
    new_subdir = submods_dir / f"jawm_{module_name}_submodule"
    try:
        if old_subdir.exists():
            old_subdir.rename(new_subdir)
            print(f"📁 Renamed submodule dir: jawm_demo_submodule → jawm_{module_name}_submodule")
        else:
            new_subdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"⚠️ Failed to rename submodule directory: {e}")

    try:
        src_submodule_py = new_subdir / "demo_submodule.py"
        dst_submodule_py = new_subdir / f"{module_name}_submodule.py"
        if src_submodule_py.exists():
            src_submodule_py.rename(dst_submodule_py)
            print(f"📄 Renamed demo_submodule.py → {module_name}_submodule.py")
    except Exception as e:
        print(f"⚠️ Failed to rename submodule file: {e}")

    # Replace references across files
    def _replace(org: str, new: str):
        for path in target.rglob("*"):
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8")
                    path.write_text(text.replace(org, new), encoding="utf-8")
                except Exception:
                    pass

    _replace("demo", module_name)
    _replace("demo.py", f"{module_name}.py")
    _replace("jawm_demo", repo_name)
    _replace("jawm_demo_submodule", f"jawm_{module_name}_submodule")
    _replace("demo_submodule.py", f"{module_name}_submodule.py")
    _replace("demo_submodule", f"{module_name}_submodule")

    # --- If user != default, adjust test workflow to use modules.yaml instead of modules.webhook.yaml ---
    if ( user != "mpg-age-bioinformatics") or ( server == "local" ):
        wf = target / ".github" / "workflows" / "test.yaml"
        if wf.exists():
            try:
                text = wf.read_text(encoding="utf-8")
                text = text.replace("modules.webhook.yaml", "modules.yaml")
                wf.write_text(text, encoding="utf-8")
                print("🔧 Updated test workflow to use modules.yaml (non-default user).")
            except Exception as e:
                print(f"⚠️ Failed to modify .github/workflows/test.yaml: {e}")


    # Remove lines 3–6 from README.md
    readme = target / "README.md"
    if readme.exists():
        try:
            lines = readme.read_text(encoding="utf-8").splitlines()
            readme.write_text("\n".join(lines[:2] + lines[6:]) + "\n", encoding="utf-8")
            print("🧹 Cleaned README.md (removed template header block)")
        except Exception as e:
            print(f"⚠️ Failed to process README.md: {e}")

    # ==== NEW: edit tests.txt (truncate after 'Main workflow test;') ====
    tests_txt = target / "test" / "tests.txt"
    if tests_txt.exists():
        try:
            content = tests_txt.read_text(encoding="utf-8")
            # Replace any 'Main workflow test;...' on a line with just 'Main workflow test;'
            content = re.sub(r'(Main workflow test;)[^\n]*', r'\1', content)
            tests_txt.write_text(content, encoding="utf-8")
            print("✂️  Updated test/tests.txt (trimmed after 'Main workflow test;').")
        except Exception as e:
            print(f"⚠️ Failed to update test/tests.txt: {e}")

    # Remove unwanted template files (including apptainer-related tests)
    for rel in [
        "notebook.ipynb",
        "notebook.py",
        ".github/workflows/apptainer.yaml",
        ".github/workflows/python.yaml",
        "test/apptainer.txt",
        "test/yaml/apptainer.yaml",
        "main.py"
    ]:
        p = target / rel
        if p.exists():
            try:
                p.unlink() if p.is_file() or p.is_symlink() else shutil.rmtree(p, ignore_errors=True)
                print(f"🗑️ Removed {rel}")
            except Exception as e:
                print(f"⚠️ Failed to remove {rel}: {e}")

    # -------------------------
    # GIT: init + add remote (SSH) + PUSH
    # -------------------------
    def _git(*args):
        try:
            subprocess.run(["git", *args], cwd=target, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True, None
        except FileNotFoundError:
            return False, "git not installed"
        except subprocess.CalledProcessError as e:
            return False, e.stderr.decode(errors="replace")

    print(f"🌱 Initializing Git repository in {target}")
    ok, err = _git("init", "-b", "main")
    if ok:
        _git("add", "-A")
        commit_ok, commit_err = _git("commit", "-m", "Initial commit (scaffolded by jawm init)")
        if not commit_ok:
            print(f"⚠️ Initial commit skipped/failed: {commit_err}")
        if server != "local" and remote_url:
            add_ok, add_err = _git("remote", "add", "origin", remote_url)
            if add_ok:
                print(f"🔗 Set remote 'origin' → {remote_url}")
                # Attempt to push current code
                push_ok, push_err = _git("push", "-u", "origin", "main")
                if push_ok:
                    print("🚀 Pushed initial commit to origin/main.")
                else:
                    print(f"⚠️ Push failed: {push_err}")
            else:
                print(f"⚠️ Could not set remote: {add_err}")
    else:
        print(f"⚠️ Git init skipped: {err}")

    print(f"\n✅ Project initialized at: {target}\n")
    print(f"💻 Test it with docker by running:\n")
    print(f" $ cd {repo_name} && jawm {module_name}.py -p ./yaml/docker.yaml\n")
    print(f"💻 or by using the jawm-test utility:\n")
    print(f" $ cd {repo_name} && jawm-test\n")

# ----------------------------------------------------------
#  Main method for jawm-dev command
# ----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="jawm-dev - Developer CLI for the jawm workflow manager")
    parser.add_argument("command", nargs="?", help="Developer command to execute (init, download, test, help)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the command")
    parser.add_argument("-V", "--version", action="version", version=f"jawm-dev {_VERSION}", help="Show jawm-dev version and exit")

    args = parser.parse_args()

    if args.command is None:
        # No command → show help
        parser.print_help()
        sys.exit(2)
    
    elif args.command == "init":
        # Subparser for the init command (positional module name)
        init_parser = argparse.ArgumentParser(
            prog="jawm-dev init",
            description="Initialize a new jawm workflow project from the jawm_template repository.",
        )
        init_parser.add_argument(
            "name",
            nargs="?",
            help="Base module name (without prefix). Example: 'demo' → repo 'jawm_demo', file 'demo.py'.",
        )
        init_parser.add_argument(
            "-s", "--server",
            default="github.com",
            help="Git server host or URL (use 'local' to skip remote). Default: github.com",
        )
        init_parser.add_argument(
            "-u", "--user",
            default="mpg-age-bioinformatics",
            help="Git username/organization for remote. Default: mpg-age-bioinformatics",
        )
        init_parser.add_argument(
            "-p", "--prefix", "--module-prefix",
            dest="module_prefix",
            default="jawm_",
            help="Repository directory prefix. Default: jawm_",
        )

        # If no args (no name provided), show help instead of error
        if not args.args:
            init_parser.print_help()
            sys.exit(0)

        init_args = init_parser.parse_args(args.args)

        if not init_args.name:
            init_parser.error("the following arguments are required: name")

        _run_init(
            module_name=init_args.name,
            server=init_args.server,
            user=init_args.user,
            module_prefix=init_args.module_prefix,
        )
        sys.exit(0)

    # elif args.command == "nf2jm":
    #     # Subparser for the init command (positional module name)
    #     nf2jm_parser = argparse.ArgumentParser(
    #         prog="jawm-dev nf2jm",
    #         description="Convert a Nextflow repo (URL or path) into a JAWM mirror.",
    #     )
    #     nf2jm_parser.add_argument(
    #         "-s", "--source",
    #         required=True,
    #         help="GitHub URL, git URL, or local path to a Nextflow repo.",
    #     )
    #     nf2jm_parser.add_argument(
    #         "-o", "--out",
    #         required=True,
    #         help="Output directory for the generated JAWM mirror",
    #     )
    #     nf2jm_parser.add_argument(
    #         "-m", "--module",
    #         help="Python module name to generate (default: derived from repo name)",
    #     )

    #     # If no args (no name provided), show help instead of error
    #     if not args.args:
    #         init_parser.print_help()
    #         sys.exit(0)

    #     nf2jm_args = nf2jm_parser.parse_args(args.args)

    #     if not nf2jm_args.name:
    #         nf2jm_parser.error("the following arguments are required: name")

    #     # _run_nf2jm(
    #     #     source=nf2jm_args.source,
    #     #     out=nf2jm_args.out,
    #     #     module=nf2jm_args.module,
    #     # )
    #     sys.exit(0)


   
    elif args.command not in _VALID_CMDS:
        # Unknown command → custom error + help
        print(f"Unknown jawm-dev command: {args.command}")
        print(f"Available jawm-dev commands: {', '.join(sorted(_VALID_CMDS))}")
        parser.print_help()
        sys.exit(2)
    
    else:
        # Known-but-unimplemented
        print(f"Command '{args.command}' is not implemented yet.")
        sys.exit(1)