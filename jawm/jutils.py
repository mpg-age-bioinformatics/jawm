"""
JAWM Utility Functions
======================

This module provides utility functions to support common operations in JAWM workflows.
Can be called with `jawm.jutils.method_name()`.

"""

import os
import yaml
import fnmatch
import inspect
from .process import Process


def read_variables(file_or_list_or_dir, process_name=None, output_type="var", namespace=None):
    """
    Load script_variables from YAML(s), .rc, or directory containing YAMLs and optionally inject them as Python variables.

    Parameters
    ----------
    file_or_list_or_dir : str | list[str]
        Path to YAML(s), RC file, or directory containing YAMLs.

    process_name : str, optional
        If set, includes matching process-scoped script_variables. Wildcards supported.

    output_type : str, default="var"
        "var" → inject as Python variables (into globals or passed namespace).
        "dict" → return as a dict only, no variable injection.

    namespace : dict, optional
        Namespace (usually locals() or globals()) to inject into. Only used when output_type="var".

    Returns
    -------
    dict
        Merged script_variables (always returned).
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
                        if scope == "global" and "script_variables" in entry:
                            vars_dict.update(entry["script_variables"])
                        elif scope == "process" and process_name and "script_variables" in entry:
                            if name and fnmatch.fnmatch(name, process_name):
                                vars_dict.update(entry["script_variables"])
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



def batch_process_file(
    directory,
    process_template=None,
    include="*",
    exclude=None,
    recursive=False,
    execute=True,
    filename_prefix="batch_",
    filename_identifier="filename"
):
    """
    Create (and optionally execute) a Process per file in a directory.

    This utility simplifies batch creation of JAWM Process instances from input files in a folder.
    Each file will generate its own Process with a unique name and script variable `INPUT_FILE`.

    Parameters
    ----------
    directory : str
        Path to the directory containing input files.

    process_template : dict
        Dictionary of base Process parameters applied to each created Process.
        - The special variable `{{INPUT_FILE}}` in the script will be replaced with the current file's path by default.

    include : str or list[str], default="*"
        fnmatch pattern(s) to include (e.g., "*.fastq", ["*.fq", "*.fastq.gz"]). Default includes all files.

    exclude : str or list[str], optional
        fnmatch pattern(s) to exclude certain files.

    recursive : bool, default=False
        Whether to search subdirectories.

    execute : bool, default=True
        If True, immediately execute each created Process.

    filename_prefix : str, default="batch_"
        Prefix added to the generated process name.

    filename_identifier : str, default="filename"
        How to generate the process name:
        - "filename": base filename without extension
        - "index": numeric index (zero-padded)
        - "filename_index": e.g., "003_sample1"

    Returns
    -------
    list[Process]
        The list of created Process instances.

    Example Use
    -----------
    >>> batch_p = jawm.jutils.batch_process_file(
    ...     directory="inputs/",
    ...     process_template={
    ...         "script": \"\"\"#!/bin/bash
    echo "Processing {{INPUT_FILE}}"
    \"\"\",
    ...         "manager": "local"
    ...     },
    ...     include="*.fastq",
    ...     filename_prefix="qc_",
    ...     filename_identifier="filename_index"
    ... )

    """
    if not os.path.isdir(directory):
        raise ValueError(f"Invalid directory: {directory}")

    include = [include] if isinstance(include, str) else include
    exclude = [exclude] if exclude else []
    exclude = [exclude] if isinstance(exclude, str) else exclude

    collected = []
    for root, _, files in os.walk(directory):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, directory)
            if not any(fnmatch.fnmatch(rel_path, pat) for pat in include):
                continue
            if any(fnmatch.fnmatch(rel_path, pat) for pat in exclude):
                continue
            collected.append((full_path, rel_path))
        if not recursive:
            break

    collected = sorted(collected, key=lambda x: x[1])
    processes = []

    for idx, (full_path, rel_path) in enumerate(collected):
        filebase = os.path.splitext(os.path.basename(full_path))[0]
        identifier = {
            "filename": filebase,
            "index": f"{idx:03d}",
            "filename_index": f"{idx:03d}_{filebase}"
        }.get(filename_identifier, filebase)

        proc_name = f"{filename_prefix}{identifier}"

        params = dict(process_template or {})
        params["name"] = proc_name
        params.setdefault("script_variables", {})["INPUT_FILE"] = full_path

        proc = Process(**params)
        processes.append(proc)

        if execute:
            proc.execute()

    return processes
