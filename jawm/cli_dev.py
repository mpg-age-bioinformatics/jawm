import argparse
import subprocess
import sys
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

# ----------------------------------------------------------
#  Main method for jawm-dev command
# ----------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="jawm-dev - Developer CLI for the jawm workflow manager")
    parser.add_argument("command", nargs="?", help="Developer command to execute (init, download, test, help)")
    # parser.add_argument("--script", default="./test/test.sh", help="Path to test.sh script (default: ./test/test.sh)")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the command")
    parser.add_argument("-V", "--version", action="version", version=f"jawm-dev {_VERSION}", help="Show jawm-dev version and exit")

    args = parser.parse_args()

    if args.command is None:
        # No command → show help
        parser.print_help()
        sys.exit(2)
    
    elif args.command == "init":
        # Operation for command jawm-dev init
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