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
import json
import stat
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
                 consider_name=True):
    """Hash the canonical jawm-file-manifest-v2 encoding of a file set.

    Entries contain relative path, byte size and per-file SHA-256. Paths are
    relative to the common root of selected directories and explicit files'
    parents, making a relocated dataset stable. Input order and duplicate
    selections do not matter. Empty files count; empty directories do not.
    Explicit consider_name=False omits paths but still frames each file.
    Missing/unreadable paths, symlinks and non-regular files raise errors.
    Extension filters apply inside directories (explicit files remain included).
    This encoding intentionally changes all legacy aggregate baselines.
    """
    if isinstance(paths, (str, Path)):
        paths = [paths]
    paths = sorted(set(os.path.abspath(p) for p in paths))
    exclude_dirs = exclude_dirs or []
    exclude_files = exclude_files or []
    extensions = {(e if e.startswith('.') else '.' + e).lower()
                  for e in allowed_extensions or []}
    selected = set()
    roots = []

    def excluded(name, patterns):
        return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)

    def checked_stat(path):
        info = os.lstat(path)
        if stat.S_ISLNK(info.st_mode):
            raise ValueError(f"Cannot hash symbolic link: {path}")
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ValueError(f"Cannot hash non-regular file: {path}")
        return info

    def walk_error(error):
        raise error

    for path in paths:
        info = checked_stat(path)
        if stat.S_ISREG(info.st_mode):
            roots.append(os.path.dirname(path))
            if not excluded(os.path.basename(path), exclude_files):
                selected.add(path)
            continue
        roots.append(path)
        for root, dirs, files in os.walk(path, onerror=walk_error):
            dirs[:] = sorted(d for d in dirs if not excluded(d, exclude_dirs)) if recursive else []
            for dirname in dirs:
                checked_stat(os.path.join(root, dirname))
            for name in sorted(files):
                if excluded(name, exclude_files):
                    continue
                if extensions and os.path.splitext(name)[1].lower() not in extensions:
                    continue
                file_path = os.path.join(root, name)
                checked_stat(file_path)
                selected.add(file_path)

    common_root = os.path.commonpath(roots) if roots else None
    entries = []
    for path in sorted(selected):
        checked_stat(path)
        digest = hashlib.sha256()
        size = 0
        with open(path, "rb") as f:
            before = os.fstat(f.fileno())
            for block in iter(lambda: f.read(1024 * 1024), b""):
                size += len(block)
                digest.update(block)
            after = os.fstat(f.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns) or size != after.st_size:
            raise OSError(f"File changed while hashing: {path}")
        entry = [size, digest.hexdigest()]
        if consider_name:
            entry.insert(0, Path(os.path.relpath(path, common_root)).as_posix())
        entries.append(entry)
    entries.sort()
    payload = json.dumps(["jawm-file-manifest-v2", bool(consider_name), entries],
                         ensure_ascii=True, separators=(",", ":")).encode("ascii")
    aggregate = hash_func()
    aggregate.update(payload)
    return aggregate.hexdigest()


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