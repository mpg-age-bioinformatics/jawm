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
from pathlib import Path
from ._utils import read_variables


__all__ = ["read_variables", "batch_process_file", "script_to_yaml"]


# ------------------------------------------------------------
#   Create (and/or execute) a Process per file in a directory
# ------------------------------------------------------------

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
    from .process import Process

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


# ------------------------------------------------------------
#   Convert a script into a JAWM parameter YAML entry
# ------------------------------------------------------------

def script_to_yaml(
    script_path=None,
    *,
    script_text=None,
    name=None,
    output_file=None,
    inline=True,
    shebang=True,
    language=None,
    scope="process",
    **kwargs
):
    """
    Convert a Python/R/Shell script into a JAWM parameter YAML entry.

    By default, the script is embedded inline as a literal block (script: | …)
    with proper indentation so you can use the result directly as a param_file.

    Args:
        script_path: Path to a script file (.py, .R, .sh, .bash, .zsh, …).
        script_text: Raw script text (use when you don't have a file).
        name: Process name to use; defaults to the file's basename without extension,
              or "script_process" if only script_text is provided.
        output_file: If set, write the YAML to this path and return the path.
        inline: If True (default), embed the script under `script: |`.
                If False, use `script_file: <path>` (requires script_path).
        shebang: If True (default) ensure/insert a shebang inferred from file
                 extension or `language`. If a string (e.g. "#!/usr/bin/env python3"
                 or "python3"), use it as the shebang (override or insert).
                 If False, do nothing.
        language: Infer the shebang if extension is ambiguous or shebang is not provided.
        scope: YAML scope, default "process".
        **kwargs: Can pass any other jawm Process parameters as well (e.g. manager="local")

    Returns:
        The YAML string (unless output_file is set, in which case the output path).

    Examples:
        >>> # Inline YAML from a file
        >>> yaml_text = jutils.script_to_yaml("scripts/hello.py")

        >>> # Write YAML to a file
        >>> jutils.script_to_yaml("scripts/run.sh", output_file="params/run.yaml")

        >>> # Reference script_file instead of embedding the script
        >>> jutils.script_to_yaml("scripts/run.sh", inline=False)

        >>> # From raw text (force python shebang)
        >>> jutils.script_to_yaml(script_text="print('hi')\\n", name="hello_py", language="python")
    """

    # --- ensure literal block style '|' for script ---------------------------
    class _LiteralString(str):
        pass

    def _literal_representer(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")

    yaml.add_representer(_LiteralString, _literal_representer)

    if not (script_path or script_text):
        raise ValueError("Provide either script_path or script_text")

    ext = None
    if script_path:
        p = Path(script_path)
        if not p.exists():
            raise FileNotFoundError(f"Script not found: {script_path}")
        if name is None:
            name = p.stem
        script_text = p.read_text()
        ext = p.suffix.lower()
    else:
        if name is None:
            name = "script_process"

    def _apply_shebang(text, ext, lang, shebang):
        if shebang is False or not text:
            return text
        # If a custom shebang string is provided, normalize it.
        if isinstance(shebang, str) and shebang.strip():
            sb = shebang.strip()
            if not sb.startswith("#!"):
                if "/" in sb or sb.startswith(("usr", "bin", "env ")):
                    sb = ("#!" if sb.startswith("/") else "#!/") + sb
                else:
                    sb = "#!/usr/bin/env " + sb
        else:
            # shebang=True -> infer from extension/language
            lang = (lang or "").lower()
            if lang in ("python", "python3", "py") or ext == ".py":
                sb = "#!/usr/bin/env python3"
            elif lang in ("r", "rscript") or ext in (".r",):
                sb = "#!/usr/bin/env Rscript"
            elif lang in ("zsh",) or ext == ".zsh":
                sb = "#!/usr/bin/env zsh"
            elif lang in ("bash",) or ext in (".sh", ".bash"):
                sb = "#!/bin/bash"
            else:
                sb = "#!/bin/bash"
        lines = text.split("\n")
        if lines and lines[0].startswith("#!"):
            lines[0] = sb
        else:
            lines.insert(0, sb)
        return "\n".join(lines)

    # normalize newlines and ensure shebang if requested
    script_text = (script_text or "").replace("\r\n", "\n").replace("\r", "\n")
    script_text = _apply_shebang(script_text, ext, language, shebang)

    entry = {"scope": scope, "name": name}
    # merge arbitrary user params like logs_directory="logsd", manager="local", etc.
    if kwargs:
        forbidden = {"script", "script_file"}
        bad = forbidden.intersection(kwargs)
        if bad:
            raise ValueError(f"These keys are reserved and cannot be set: {sorted(bad)}")
        entry.update(kwargs)

    if inline:
        # ensure trailing newline inside the block for cleaner diffs
        entry["script"] = _LiteralString(script_text.rstrip("\n") + "\n")
    else:
        if not script_path:
            raise ValueError("inline=False requires script_path (to set script_file)")
        entry["script_file"] = str(Path(script_path))

    yaml_obj = [entry]
    yaml_str = yaml.dump(
        yaml_obj,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
        width=4096,
        allow_unicode=True,
    )

    if output_file:
        outp = Path(output_file)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(yaml_str)
        return str(outp)

    return yaml_str

