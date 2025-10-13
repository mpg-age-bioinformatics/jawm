import argparse
import sys


# --- Version detection (module scope) ---
try:
    from importlib import metadata as md  # py>=3.8
except Exception:
    import importlib_metadata as md

_PKG_NAME = (__package__ or "jawm").split(".")[0]

try:
    _VERSION = md.version(_PKG_NAME)
except md.PackageNotFoundError:
    _VERSION = "dev" 


def main():
    parser = argparse.ArgumentParser(description="jawm-dev - Developer CLI for the jawm workflow manager")
    parser.add_argument("command", nargs="?", choices=["init", "download", "test", "help"], help="Developer command to execute (init, download, test, help)")
    parser.add_argument("-V", "--version", action="version", version=f"jawm-dev {_VERSION}", help="Show jawm-dev version and exit")

    args = parser.parse_args()