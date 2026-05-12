"""
_internal utility functions for jawm
====================================

This module contains internal helper functions used across the jawm system.
These are not part of the public API and are intended for use within core modules
like `process.py`, `jutils.py`, and others.

"""

import os
import yaml
import fnmatch
import inspect
import hashlib
from pathlib import Path


def read_variables(file_or_list_or_dir, process_name=None, output_type="var", namespace=None):
    """
    Load var from YAML(s), .rc, or directory containing YAMLs and optionally inject them as Python variables.

    Parameters
    ----------
    file_or_list_or_dir : str | list[str]
        Path to YAML(s), RC file, or directory containing YAMLs.

    process_name : str, optional
        If set, includes matching process-scoped var. Wildcards supported.

    output_type : str, default="var"
        "var" → inject as Python variables (into globals or passed namespace).
        "dict" → return as a dict only, no variable injection.

    namespace : dict, optional
        Namespace (usually locals() or globals()) to inject into. Only used when output_type="var".

    Returns
    -------
    dict
        Merged var (always returned).
    """
    def load_single_file(path, process_name=None):
        ext = os.path.splitext(path)[1].lower()
        vars_dict = {}

        with open(path, "r") as f:
            if ext in [".yaml", ".yml"]:
                parsed = yaml.safe_load(f)
                if isinstance(parsed, dict):
                    # parsed = _expand_relpaths_in_value(parsed, os.getcwd())
                    vars_dict.update(parsed)
                elif isinstance(parsed, list):
                    for entry in parsed:
                        if not isinstance(entry, dict):
                            continue
                        scope = entry.get("scope")
                        name = entry.get("name", "")
                        if scope == "global" and "var" in entry:
                            vars_dict.update(entry["var"])
                        elif scope == "process" and process_name and "var" in entry:
                            names = name if isinstance(name, (list, tuple)) else [name]
                            for n in names:
                                if n and fnmatch.fnmatch(process_name, n):
                                    vars_dict.update(entry["var"])
                                    break
            else:
                for line in f:
                    if line.strip() and "=" in line:
                        key, val = line.strip().split("=", 1)
                        val = val.strip().strip('"').strip("'")
                        vars_dict[key.strip()] = val

        return _expand_relpaths_in_value(vars_dict, os.getcwd())

    # Gather all relevant files
    all_files = []
    if isinstance(file_or_list_or_dir, str):
        if os.path.isdir(file_or_list_or_dir):
            all_files = sorted([
                os.path.join(file_or_list_or_dir, f)
                for f in os.listdir(file_or_list_or_dir)
                if f.endswith((".yaml", ".yml"))
            ])
        else:
            all_files = [file_or_list_or_dir]
    elif isinstance(file_or_list_or_dir, list):
        for item in file_or_list_or_dir:
            if os.path.isfile(item):
                all_files.append(item)

    # Merge variables
    merged_vars = {}
    for file in all_files:
        if os.path.exists(file):
            merged_vars.update(load_single_file(file, process_name))
        else:
            raise FileNotFoundError(f"Variable file not found: {file}")

    # Optional injection
    if output_type == "var":
        target = namespace or inspect.currentframe().f_back.f_globals
        for k, v in merged_vars.items():
            target[k] = v

    return merged_vars


def hash_content(paths, hash_func=hashlib.sha256,
                 exclude_dirs=None, exclude_files=None,
                 allowed_extensions=None, recursive=True,
                 consider_name=False):
    """
    Return a combined hash digest for multiple files and/or folders,
    including their contents and (optionally) their basenames.

    The traversal order is deterministic across platforms: top-level paths
    are processed in the order given, and within each directory both
    subdirectories and files are visited in sorted order.

    When `consider_name=True`, only the file's basename is included in the
    hash — never its parent directories or absolute path. This means hashing
    a file directly and hashing it as part of a containing directory record
    the same name for that file.

    Args:
        paths (str or Path or list[str | Path]): A single file/folder path or
            a list of paths to include in the hash.
        hash_func (callable, optional): Hash function from hashlib (default: sha256).
        exclude_dirs (list[str], optional): List of directory name patterns to exclude.
        exclude_files (list[str], optional): List of file name patterns to exclude.
        allowed_extensions (list[str], optional): Only consider allowed files if a directory is provided.
        recursive (bool, optional): Whether to descend into subdirectories (default: True).
        consider_name (bool, optional): Whether to consider file basenames while hashing (default: False).

    Returns:
        str: Hex digest representing the combined hash of all provided files
            and folder contents.
    """
    if exclude_dirs is None:
        exclude_dirs = []
    if exclude_files is None:
        exclude_files = []

    if isinstance(paths, (str, Path)):
        paths = [paths]

    # Normalize extension list
    allowed_exts = None
    if allowed_extensions:
        allowed_exts = {
            (e if e.startswith(".") else "." + e).lower()
            for e in allowed_extensions
        }

    def _file_excluded(name):
        return any(fnmatch.fnmatch(name, pat) for pat in exclude_files)

    def _dir_excluded(name):
        return any(fnmatch.fnmatch(name, pat) for pat in exclude_dirs)

    def _ext_allowed(name):
        if allowed_exts is None:
            return True
        return os.path.splitext(name)[1].lower() in allowed_exts

    def _hash_file(h, fpath, name_to_record=None):
        if name_to_record is not None and consider_name:
            h.update(name_to_record.encode("utf-8"))
        with open(fpath, "rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)

    h = hash_func()

    for path in paths:
        path = os.path.abspath(path)

        if os.path.isfile(path):
            fname = os.path.basename(path)
            if _file_excluded(fname):
                continue
            _hash_file(h, path, name_to_record=fname)

        elif os.path.isdir(path):
            if recursive:
                walker = os.walk(path)
            else:
                entries = os.listdir(path)
                files_only = [
                    e for e in entries
                    if os.path.isfile(os.path.join(path, e))
                ]
                walker = [(path, [], files_only)]

            for root, dirs, files in walker:
                if recursive:
                    dirs[:] = sorted(d for d in dirs if not _dir_excluded(d))

                for fname in sorted(files):
                    if _file_excluded(fname):
                        continue
                    if not _ext_allowed(fname):
                        continue

                    fpath = os.path.join(root, fname)
                    # Record the basename only — matches the standalone-file branch
                    _hash_file(h, fpath, name_to_record=fname)

        else:
            continue

    return h.hexdigest()


def _sanitize_vars(d, prefixes=("mk.", "map.")):
    """
    Return a copy suitable for injecting into a Python exec namespace:
    - For keys starting with any of `prefixes`, drop the first segment (e.g., mk.output -> output).
    - Leave other keys as-is.
    """
    out = {}
    for k, v in (d or {}).items():
        for p in prefixes:
            if isinstance(k, str) and k.startswith(p):
                out[k.split(".", 1)[-1]] = v
                break
        else:
            out[k] = v
    return out


def _add_prefix_aliases(d, prefixes=("mk.", "map.")):
    """
    In-place: for each key starting with any prefix, also add an alias
    without the first segment (e.g., mk.output -> output) if missing.
    """
    if not isinstance(d, dict):
        return d
    for k in list(d.keys()):
        if isinstance(k, str):
            for p in prefixes:
                if k.startswith(p):
                    short = k.split(".", 1)[-1]
                    d.setdefault(short, d[k])
                    break
    return d


def _expand_relpaths_in_value(val, cwd=None, skip_keys=None):
    r"""
    Expand path prefixes in strings recursively.

    Supported expansions:
    - './' → <cwd>/
    - '\./' → literal './'
    - '../' -> normalized relative to <cwd>
    - '~/': expanded to user home only if JAWM_EXPAND_HOME=true

    Controlled by environment variables:
    ------------------------------------
    JAWM_EXPAND_PATH=true|false   # Enable/disable './' expansion
    JAWM_EXPAND_HOME=true|false   # Enable/disable '~/'

    Parameters
    ----------
    val : any
        Input value (str, dict, list, or tuple).
    cwd : str, optional
        Base directory for relative expansion (default: os.getcwd()).
    skip_keys : set[str] | None
        Dict keys to skip during recursion.

    Returns
    -------
    any
        Expanded value (same structure as input).
    """
    import os

    # Environment flags
    expand_path = os.getenv("JAWM_EXPAND_PATH", "true").strip().lower() not in ("false", "0", "no")
    expand_home = os.getenv("JAWM_EXPAND_HOME", "false").strip().lower() in ("true", "1", "yes")

    if not expand_path and not expand_home:
        return val  # skip all expansions entirely

    if cwd is None:
        cwd = os.getcwd()

    if isinstance(val, str):
        if val.startswith(r"\./"):
            return val[1:]  # literal './'

        if expand_path and (val.startswith("./") or val.startswith("../")):
            return os.path.abspath(os.path.join(cwd, val))

        if expand_home and val.startswith("~/"):
            return os.path.expanduser(val)

        return val

    if isinstance(val, dict):
        return {
            k: _expand_relpaths_in_value(v, cwd, skip_keys)
            if not (skip_keys and k in skip_keys)
            else v
            for k, v in val.items()
        }

    if isinstance(val, (list, tuple)):
        converted = [_expand_relpaths_in_value(x, cwd, skip_keys) for x in val]
        return type(val)(converted) if isinstance(val, tuple) else converted

    return val