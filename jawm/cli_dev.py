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

_TEMPLATE_ZIP = "https://github.com/mpg-age-bioinformatics/jawm_template/archive/refs/heads/main.zip"

def _run_init(repo_name):
    """
    Initialize a new jawm workflow project by downloading the official template ZIP.
    No git required.

    Steps:
    1. Download template archive from GitHub.
    2. Extract into <repo_name> directory.
    3. Remove Git metadata if any.
    4. Update template references
    5. Confirm successful setup.
    """
    target = Path(repo_name).resolve()

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

        # Rename extracted directory
        shutil.move(str(temp_extract), str(target))

    except Exception as e:
        print(f"❌ Failed to download or extract template: {e}")
        sys.exit(1)

    # Remove any leftover Git metadata from the template
    git_cleanup = {".git", ".gitignore"}
    for git_item in git_cleanup:
        path = target / git_item
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except Exception:
                    pass

    # --- Rename template.py to <repo_name>.py ---
    template_file = target / "template.py"
    renamed_file = target / f"{repo_name}.py"
    if template_file.exists():
        try:
            template_file.rename(renamed_file)
            print(f"📄 Renamed template.py → {repo_name}.py")
        except Exception as e:
            print(f"⚠️ Failed to rename template.py: {e}")

    # --- Update template references ---
    def _replace_template_strings(org, new):
        """Recursively replace 'template.py' → '<repo_name>.py' and '_template' → '<repo_name>' in all files."""
        root_dir = Path(target)
        for path in root_dir.rglob("*"):
            if path.is_file():
                try:
                    text = path.read_text(encoding="utf-8")
                    text = text.replace(org, new)
                    path.write_text(text, encoding="utf-8")
                except Exception:
                    pass
    _replace_template_strings("template.py", f"{repo_name}.py")
    _replace_template_strings("_template", repo_name)

    print(f"\n✅ New jawm project initialized at: {target}")
    print(f"   You can now edit and customize your jawm project: {repo_name}.")
    print(f"   Run `jawm {repo_name}.py` to test it from the project directory.")


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
        # Subparser for the init command (positional project name)
        init_parser = argparse.ArgumentParser(prog="jawm-dev init", description="Initialize a new jawm workflow project from the jawm_template repository.")
        init_parser.add_argument("name", nargs="?", help="Name of the new workflow project directory to create.")
        init_args = init_parser.parse_args(args.args)

        # If no args (no name provided), show help instead of error
        if not args.args:
            init_parser.print_help()
            sys.exit(0)

        init_args = init_parser.parse_args(args.args)
        _run_init(init_args.name)
        sys.exit(0)

   
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