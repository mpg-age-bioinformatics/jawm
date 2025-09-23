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
                            if name and fnmatch.fnmatch(process_name, name):
                                vars_dict.update(entry["var"])
            else:
                for line in f:
                    if line.strip() and "=" in line:
                        key, val = line.strip().split("=", 1)
                        val = val.strip().strip('"').strip("'")
                        vars_dict[key.strip()] = val

        return vars_dict

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
                 allowed_extensions=None, recursive=True):
    """
    Return a combined hash digest for multiple files and/or folders,
    including their contents and structure, excluding specified directories
    and files, optionally consider only allowed extention in case of directory .

    Args:
        paths (str or Path or list[str | Path]): A single file/folder path or 
            a list of paths to include in the hash.
        hash_func (callable, optional): Hash function from hashlib (default: sha256).
        exclude_dirs (list[str], optional): List of directory name patterns to exclude.
        exclude_files (list[str], optional): List of file name patterns to exclude.
        allowed_extensions (list[str], optional): Only consider allowed files if a directory provided.
        recursive (bool, optional): Whether to descend into subdirectories (default: True).

    Returns:
        str: Hex digest representing the combined hash of all provided files
            and folder contents/structure.

    Example:
        >>> hash_content(["/data/folder1", "/data/file.txt"])
        '5d41402abc4b2a76b9719d911017c592'
    """
    if exclude_dirs is None:
        exclude_dirs = []
    if exclude_files is None:
        exclude_files = []

    if isinstance(paths, (str, Path)):
        paths = [paths]

    # Normalize ext list
    allowed_exts = None
    if allowed_extensions:
        allowed_exts = set(e.lower() if e.startswith(".") else "." + e.lower() for e in allowed_extensions)

    h = hash_func()

    for path in paths:
        path = os.path.abspath(path)

        if os.path.isfile(path):
            # Handle individual file
            fname = os.path.basename(path)
            if any(fnmatch.fnmatch(fname, pat) for pat in exclude_files):
                continue
            h.update(fname.encode())
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)

        elif os.path.isdir(path):
            # Handle folder
            if recursive:
                walker = os.walk(path)
            else:
                # Top-level only: mimic os.walk but with no subdirs
                walker = [(path, [], os.listdir(path))]

            for root, dirs, files in walker:
                if recursive:
                    dirs[:] = [d for d in dirs 
                               if not any(fnmatch.fnmatch(d, pat) for pat in exclude_dirs)]

                for fname in sorted(files):
                    # Skip excluded files
                    if any(fnmatch.fnmatch(fname, pat) for pat in exclude_files):
                        continue

                    # If extensions are restricted, keep only matching ones
                    if allowed_exts is not None:
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in allowed_exts:
                            continue

                    fpath = os.path.join(root, fname)
                    relpath = os.path.relpath(fpath, path)

                    # Include relative path
                    h.update(relpath.encode())

                    # Include file content
                    with open(fpath, "rb") as f:
                        while chunk := f.read(8192):
                            h.update(chunk)
        else:
            # Skip non-existent paths
            continue

    return h.hexdigest()
