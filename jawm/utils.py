"""
jawm Utility Functions
======================

This module provides utility functions to support common operations in jawm workflows.
Can be called with `jawm.utils.method_name()`.

"""
from __future__ import annotations
import os
import yaml
import fnmatch
import inspect
from pathlib import Path
from ._utils import read_variables, hash_content, _sanitize_vars
import subprocess
import hashlib
import fnmatch
import sys
import argparse
import glob
import importlib.util
import pathlib
import warnings
import logging


__all__ = ["read_variables", "hash_content", "batch_process_file", "script_to_yaml", "docker_available", "apptainer_available", "write_hash_file"]


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

    This utility simplifies batch creation of jawm Process instances from input files in a folder.
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
        params.setdefault("var", {})["INPUT_FILE"] = full_path

        proc = Process(**params)
        processes.append(proc)

        if execute:
            proc.execute()

    return processes


# ------------------------------------------------------------
#   Convert a script into a jawm parameter YAML entry
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
    Convert a Python/R/Shell script into a jawm parameter YAML entry.

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


def docker_available(v=False):
    """
    Check whether Docker is available on the system.

    This function attempts to run `docker --version` to verify that the Docker
    command-line tool is installed and accessible.

    Args:
        v (bool, optional): If True, prints diagnostic messages about Docker's
            availability and version. Defaults to False.

    Returns:
        bool: True if Docker is installed and responds successfully to
        `docker --version`, otherwise False.

    Example:
        >>> docker_available()
        True
        >>> docker_available(v=True)
        Docker found: Docker version 24.0.2, build cb74dfc
        True
    """
    logger = logging.getLogger("jawm.utils|docker_available")
    try:
        # Run "docker --version" to check availability
        result = subprocess.run(
            ["docker", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        if v:
            logger.info("Docker found:", result.stdout.strip())
        return True
    except FileNotFoundError:
        # "docker" command not found
        if v:
            logger.error("Docker is not installed or not in PATH.")
        return False
    except subprocess.CalledProcessError as e:
        # Docker exists but returned an error
        if v:
            logger.error("Docker command failed:", e.stderr.strip())
        return False


def apptainer_available(v=False):
    """
    Check whether Apptainer is available on the system.

    This function attempts to run `apptainer --version` to verify that the
    Apptainer command-line tool is installed and accessible.

    Args:
        v (bool, optional): If True, prints diagnostic messages about
            Apptainer's availability and version. Defaults to False.

    Returns:
        bool: True if Apptainer is installed and responds successfully to
        `apptainer --version`, otherwise False.

    Example:
        >>> apptainer_available()
        True
        >>> apptainer_available(v=True)
        Apptainer found: apptainer version 1.2.3
        True
    """
    logger = logging.getLogger("jawm.utils|apptainer_available")
    try:
        # Run "apptainer --version" to check availability
        result = subprocess.run(
            ["apptainer", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        if v:
            logger.info("Apptainer found:", result.stdout.strip())
        return True
    except FileNotFoundError:
        # "apptainer" command not found
        if v:
            logger.error("Apptainer is not installed or not in PATH.")
        return False
    except subprocess.CalledProcessError as e:
        # apptainer exists but returned an error
        if v:
            logger.error("Apptainer command failed:", e.stderr.strip())
        return False
    

def kubernetes_available(v=False):
    """
    Check whether Kubernetes (kubectl) is available on the system.

    This function attempts to run `kubectl version --client` to verify that
    the kubectl CLI tool is installed and accessible.

    Args:
        v (bool, optional): If True, prints diagnostic messages about
            kubectl's availability and version.

    Returns:
        bool: True if kubectl is installed and responds successfully,
              otherwise False.
    """
    logger = logging.getLogger("jawm.utils|kubernetes_available")
    try:
        result = subprocess.run(
            ["kubectl", "version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        if v:
            logger.info("Kubernetes available:", result.stdout.strip())
        return True
    except FileNotFoundError:
        if v:
            logger.error("kubectl is not installed or not in PATH.")
        return False
    except subprocess.CalledProcessError as e:
        if v:
            logger.error("kubectl command failed:", (e.stderr or e.stdout).strip())
        return False
    except Exception as e:
        if v:
            logger.error("Unexpected error while checking Kubernetes:", str(e))
        return False


def write_hash_file(paths, hash_file, hash_func=hashlib.sha256, 
                    v=True, exclude_dirs=None, exclude_files=None,
                    allowed_extensions=None, recursive=True,
                    consider_name=False):
    """
    Compute the combined hash of files/folders and write it to a file.
    If the file already exists, check if the stored hash matches the current hash
    and report the result.

    Args:
        paths (str | Path | list[str | Path]): File(s) and/or folder(s) to hash.
        hash_file (str | Path): Path to the file where the hash should be written.
        hash_func (callable, optional): Hash function to use (default: hashlib.sha256).
        v (bool): Print the verbose (default: True).
        exclude_dirs (list[str], optional): Directory patterns to exclude.
        exclude_files (list[str], optional): File patterns to exclude.
        allowed_extensions (list[str] | None): When hashing directories, only count these extensions.
        recursive (bool): Recurse into subdirectories (default: True).
        consider_name (bool, optional): Whether to consider the file names while hashing (default: False).

    Returns:
        bool: True if the hash was written or matched the existing hash, 
              False if the existing hash differs.
    """
    logger = logging.getLogger("jawm|[hash]")
    current_hash = hash_content(paths, hash_func=hash_func,
                                allowed_extensions=allowed_extensions, 
                                exclude_dirs=exclude_dirs, 
                                exclude_files=exclude_files,
                                recursive=recursive)
    hash_file = Path(hash_file)

    if hash_file.exists():
        stored_hash = hash_file.read_text().strip()
        if stored_hash == current_hash:
            if v:
                logger.info(f"Hash matches existing file: {hash_file}")
            return True
        else:
            if v:
                logger.warning(f"Hash differs from existing file: {hash_file}\nStored={stored_hash}\nComputed={current_hash}")
            return False
    else:
        hash_file.write_text(current_hash)
        if v:
            logger.info(f"Hash written to: {hash_file}")
        return True


def parse_arguments(available_workflows=["main"],description="A jawm module.",extra_args={}):
    """
    Parse command-line arguments to determine which workflows to run.

    This function uses argparse to read a positional argument `workflows`
    from the command line. The argument can be a single submodule name
    or a comma-separated list of workflows. It validates the input
    against a list of available workflows and exits if any invalid
    workflows are provided.

    Parameters
    ----------
    available_workflows : list of str, optional
        A list of valid submodule names that the user is allowed to run.
        Default is ["main"].

    description: str, 
        The module description.
        Default is "A jawm module.".

    extra_args: dictionary
        An { "arg":"Help text"} dictionary.
        Default is {}.

    Returns
    -------
    list of str
        A list of submodule names that were specified in the command line
        and validated against `available_workflows`.

    Raises
    ------
    SystemExit
        If any of the provided workflows are not found in `available_workflows`,
        the function prints an error message and exits the program.

    Examples
    --------
    Command line usage:
        $ python my_program.py main
        $ python my_program.py main,submodule2

    In code:
        workflows = parse_arguments(["main", "submodule2"])
    """

    logger = logging.getLogger("jawm.utils|parse_arguments")

    parser = argparse.ArgumentParser(
        description=description
    )

    
    parser.add_argument(
        "workflows",
        nargs="+",
        help="The workflows to run. Eg. 'main' for running all modules or a comma separated list of workflows."
    )
    parser.add_argument("-p", "--parameters", nargs="+", default=None, help="YAML file(s) or directory of parameter config files to be used as default param_file.")
    parser.add_argument("-v", "--variables", nargs="+", default=None, help="YAML or .rc file(s) or directory of files of script variables to inject into the module script.")
    parser.add_argument("-l", "--logs_directory", "--logs-directory", dest="logs_directory", default=None, help="Directory to store logs; sets default logs_directory. CLI logs are saved in <logs_directory>/jawm_runs (default: ./logs/jawm_runs).")
    parser.add_argument("-r", "--resume", action="store_true", default=None, help="Resume mode: skip executing already successfully completed processes.")
    parser.add_argument("-n", "--no_override", "--no-override", dest="no_override", nargs="?", const="ALL", help="Disable override for all or specific parameters (comma-separated).")
    parser.add_argument("--git-cache", help="Path for jawm's git cache (default: ~/.jawm/git)")

    for arg in list(extra_args.keys()) :
            parser.add_argument(arg, help=extra_args[arg] )

    args, unknown_args=parser.parse_known_args()
            
    workflows=args.workflows

    var=[]
    if args.parameters :
        var=var+args.parameters
    if args.variables:
        var=var+args.variables

    if var:
        var=_sanitize_vars( read_variables( var, output_type="dict" ) )
    else:
        var={}

    # script_name = os.path.basename(sys.argv[0])
    # workflows=[ s for s in workflows if s != sys.argv[0] ]
    workflows=workflows[1:]
    if not workflows :
        workflows=["main"]
    else :
        workflows=workflows[0]

        if "," in workflows :
            workflows=workflows.split(",")
        else:
            workflows=[workflows]


    
    not_found=[ s for s in workflows if s not in available_workflows ] 

    if not_found :
        logger.warning("The following workflows could not be found:", ",".join(not_found) )
        logger.info("Available workflows:", ",".join(available_workflows) )
        sys.exit(1)

    return workflows, var, args, unknown_args


from collections.abc import Iterable

def workflow(select=None, workflows=None):
    """
    Filter a list of workflows, returning only those that match the selected ones.

    Parameters
    ----------
    select : str or list, optional
        A single workflow name (string) or a list of workflow names (strings) 
        that should be kept. Defaults to an empty list if not provided.
    workflows : list, optional
        A list of available workflows to be filtered. 
        Defaults to an empty list if not provided.

    Returns
    -------
    list
        A list containing only the workflows that are present in both
        `workflows` and `select`.

    Notes
    -----
    - If `select` is a string, it will be converted into a single-element list.
    - This implementation avoids mutable default arguments (`[]`) to prevent 
      side effects across calls.
    - The order of the returned list follows the order of `workflows`.
    - Both arguments should ideally contain hashable elements (e.g., strings).

    Examples
    --------
    >>> workflow(select="wf1", workflows=["wf1", "wf2", "wf3"])
    ['wf1']

    >>> workflow(select=["wf1", "wf3"], workflows=["wf1", "wf2", "wf3"])
    ['wf1', 'wf3']

    >>> workflow(select="wfX", workflows=["wf1", "wf2"])
    []

    >>> workflow()
    []
    """
    if select is None:
        select = []
    elif isinstance(select, str):
        select = [select]

    if workflows is None:
        workflows = []

    return [s for s in workflows if s in select]

def from_file_pairs(data_folder, read1_suffix=".READ_1.fastq.gz", read2_suffix=".READ_2.fastq.gz"):
    """
    Mimics Nextflow's Channel.fromFilePairs for paired FASTQ files.

    Args:
        data_folder (str): path to folder with raw FASTQ data
        read1_suffix (str): suffix for read 1 files (default ".READ_1.fastq.gz")
        read2_suffix (str): suffix for read 2 files (default ".READ_2.fastq.gz")

    Returns:
        dict: {sample_name: [read1_path, read2_path]}
    """
    pattern_r1 = os.path.join(data_folder, f"*{read1_suffix}")
    pattern_r2 = os.path.join(data_folder, f"*{read2_suffix}")

    files_r1 = glob.glob(pattern_r1)
    files_r2 = glob.glob(pattern_r2)

    pairs = {}
    for f in files_r1:
        sample = os.path.basename(f).replace(read1_suffix, "")
        r2_match = os.path.join(data_folder, sample + read2_suffix)
        if r2_match in files_r2:
            pairs[sample] = [f, r2_match]

    return pairs

def load_modules(
    paths,
    *,
    address="github.com",
    user="mpg-age-bioinformatics",
    modules_root=None,
):
    """
    Dynamically imports Python modules or folders, safely.

    - Accepts paths or specs like "repo@ref".
    - Clones missing repos into <modules_root>/<repo>.
    - Skips re-cloning if repo exists.
    - Avoids re-importing modules already in sys.modules.
    - HTTPS→SSH fallback cloning (non-interactive).

    Path resolution:
      • Relative paths are resolved against the CALLER'S FILE directory,
        not this function's file and not necessarily the process CWD.
        (If no caller file is available, we fall back to os.getcwd().)

    Parameters
    ----------
    paths : list[str] | str
        Repositories or module paths to import (can include @ref).
    address : str
        Git host address (default: github.com).
    user : str
        Default organization or user name on the git host.
    modules_root : str | Path, optional
        Root directory where modules are cloned or searched.
        Priority:
          1. Explicit argument (resolved relative to caller file if not absolute)
          2. Environment variable JAWM_MODULES_PATH (same)
          3. Default: <caller_file_dir>/.submodules
    """
    logger = logging.getLogger("jawm.utils|load_modules")

    # ⭐ Determine the CALLER's file directory
    def _caller_dir() -> pathlib.Path:
        try:
            # Walk the stack to find the first frame outside this module.
            this_file = pathlib.Path(__file__).resolve()
            for frame_info in inspect.stack():
                fpath = pathlib.Path(frame_info.filename).resolve()
                if fpath != this_file and fpath.exists():
                    return fpath.parent
        except Exception:
            pass
        # Fallback (e.g., interactive/REPL)
        return pathlib.Path(os.getcwd()).resolve()

    caller_base = _caller_dir()

    # ⭐ Resolve a path relative to the caller's file (unless absolute)
    def _resolve_from_caller(p: pathlib.Path | str) -> pathlib.Path:
        p = pathlib.Path(p).expanduser()
        return (caller_base / p).resolve() if not p.is_absolute() else p.resolve()

    if not isinstance(paths, (list, tuple)):
        paths = [paths]

    imported_modules = []
    seen_paths = set()
    py_files = []

    # ⭐ Determine modules_root relative to CALLER
    if modules_root is not None:
        modules_root = _resolve_from_caller(modules_root)
        logger.info(f"📦 Using modules_root argument (relative to caller): {modules_root}")
    else:
        env_modules_path = os.getenv("JAWM_MODULES_PATH")
        if env_modules_path:
            modules_root = _resolve_from_caller(env_modules_path)
            logger.info(f"📦 Using JAWM_MODULES_PATH (relative to caller if not absolute): {modules_root}")
        else:
            modules_root = (caller_base / ".submodules").resolve()
            logger.info(f"📦 Using default modules directory next to caller: {modules_root}")

    modules_root.mkdir(parents=True, exist_ok=True)

    # ---------------- helpers ---------------- #

    def _compute_module_name(file_path):
        return file_path.stem

    def _parse_repo_spec(spec):
        spec_str = str(spec)
        if "@" in spec_str:
            repo, ref = spec_str.rsplit("@", 1)
            return repo.strip(), ref.strip()
        return spec_str.strip(), None

    def _run_git_command(args, cwd=None):
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "echo"
        env["SSH_ASKPASS"] = "echo"
        result = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
        )
        return result.stdout.strip()

    # helper to get latest tag from remote
    def _get_latest_tag(https_url):
        try:
            logger.info(f"🔍 Fetching latest tag from {https_url} ...")
            output = _run_git_command(["git", "ls-remote", "--tags", https_url])
            tags = []
            for line in output.splitlines():
                if "refs/tags/" in line:
                    tag = line.split("refs/tags/")[-1]
                    if tag.endswith("^{}"):
                        tag = tag[:-3]
                    tags.append(tag)
            if not tags:
                logger.warning(f"No tags found for {https_url}; using default branch.")
                return None

            import re
            def version_key(tag):
                nums = re.findall(r"\d+", tag)
                return tuple(map(int, nums)) if nums else (0,)
            latest = sorted(tags, key=version_key, reverse=True)[0]
            logger.info(f"🕓 Latest tag detected: {latest}")
            return latest
        except Exception as e:
            logger.warning(f"Failed to fetch latest tag for {https_url}: {e}")
            return None

    def _try_clone_repo(repo_name, ref=None):
        """Clone repo into <modules_root>/<repo_name> and optionally checkout ref."""
        dest_dir = modules_root / repo_name
        https_url = f"https://{address}/{user}/{repo_name}.git"
        ssh_url = f"git@{address}:{user}/{repo_name}.git"

        if ref == "latest":
            ref = _get_latest_tag(https_url)
            if not ref:
                logger.warning(f"Falling back to default branch for '{repo_name}' (no tags).")

        if dest_dir.exists():
            logger.info(f"📁 Repository '{repo_name}' already exists at {dest_dir}")
            try:
                current_head = _run_git_command(["git", "rev-parse", "HEAD"], cwd=dest_dir)
                remote_name = _run_git_command(["git", "remote"], cwd=dest_dir) or "origin"
                remote_url = _run_git_command(["git", "remote", "get-url", remote_name], cwd=dest_dir)

                try:
                    upstream_branch = _run_git_command(
                        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
                        cwd=dest_dir,
                    )
                except subprocess.CalledProcessError:
                    upstream_branch = None

                _run_git_command(["git", "fetch", "--all"], cwd=dest_dir)
                _run_git_command(["git", "fetch", "--tags"], cwd=dest_dir)

                remote_latest_commit = None
                if upstream_branch:
                    try:
                        remote_latest_commit = _run_git_command(
                            ["git", "rev-parse", upstream_branch], cwd=dest_dir
                        )
                    except subprocess.CalledProcessError:
                        remote_latest_commit = None

                if upstream_branch and remote_latest_commit:
                    logger.info(
                        f"🔹 Current HEAD: {current_head[:10]} | Remote: {remote_name} ({remote_url}) | Tracking: {upstream_branch}"
                    )
                    logger.info(f"🔸 Latest remote commit: {remote_latest_commit[:10]}")
                elif upstream_branch:
                    logger.info(
                        f"🔹 Current HEAD: {current_head[:10]} | Remote: {remote_name} ({remote_url}) | Tracking: {upstream_branch}"
                    )
                    logger.info("🔸 Latest remote commit: unavailable (fetch failed)")
                else:
                    logger.info(
                        f"🔹 Current HEAD: {current_head[:10]} | Remote: {remote_name} ({remote_url}) | No upstream tracking branch"
                    )

                if remote_latest_commit and remote_latest_commit != current_head:
                    logger.info(f"⬇️  Remote HEAD differs: {remote_latest_commit[:10]} (upstream)")
                    logger.info(f"➡️  Pulling latest changes for '{repo_name}' ...")
                    _run_git_command(["git", "pull"], cwd=dest_dir)
                    new_head = _run_git_command(["git", "rev-parse", "HEAD"], cwd=dest_dir)
                    if new_head != current_head:
                        logger.info(f"✅ '{repo_name}' updated: {current_head[:10]} → {new_head[:10]}")
                    else:
                        logger.info(f"ℹ️  '{repo_name}' already up to date.")
                else:
                    logger.info(f"✅ '{repo_name}' already up to date with remote.")

                if ref:
                    _checkout_to_ref(repo_name, dest_dir, ref, logger)
                else:
                    _checkout_to_default_head(repo_name, dest_dir, logger)

            except subprocess.CalledProcessError as e:
                logger.warning(f"Git operation failed for '{repo_name}': {e}")
            except Exception as e:
                logger.warning(f"Unexpected error while updating '{repo_name}': {e}")

            return dest_dir

        logger.info(f"🌀 Cloning '{repo_name}' via HTTPS: {https_url}")
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_ASKPASS"] = "echo"
        env["SSH_ASKPASS"] = "echo"

        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", https_url, str(dest_dir)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            logger.info(f"✅ Cloned via HTTPS into {dest_dir}")
        except subprocess.CalledProcessError:
            logger.warning(f"⚠️  HTTPS clone failed for '{repo_name}', trying SSH ...")
            try:
                subprocess.run(
                    ["git", "clone", "--depth", "1", ssh_url, str(dest_dir)],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                )
                logger.info(f"✅ Cloned via SSH into {dest_dir}")
            except subprocess.CalledProcessError as e2:
                logger.error(f"❌ Failed to clone '{repo_name}' via both HTTPS and SSH: {e2}")
                return None

        try:
            branch = _run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=dest_dir)
            head_commit = _run_git_command(["git", "rev-parse", "HEAD"], cwd=dest_dir)
            logger.info(f"📍 '{repo_name}' cloned at branch '{branch}' with HEAD {head_commit[:10]}")
        except Exception as e:
            logger.warning(f"Could not determine current HEAD for '{repo_name}': {e}")

        if ref:
            _checkout_to_ref(repo_name, dest_dir, ref, logger)
        else:
            _checkout_to_default_head(repo_name, dest_dir, logger)

        return dest_dir

    def _checkout_to_ref(repo_name, repo_path, ref, logger):
        """Checkout to commit, branch, or tag — safely and with logging."""
        try:
            logger.info(f"🔍 Preparing to checkout '{repo_name}' to ref '{ref}' ...")
            try:
                _run_git_command(["git", "fetch", "--unshallow"], cwd=repo_path)
            except subprocess.CalledProcessError:
                pass
            _run_git_command(["git", "fetch", "--all"], cwd=repo_path)
            _run_git_command(["git", "fetch", "--tags"], cwd=repo_path)

            ref_type = "unknown"
            try:
                branches = _run_git_command(["git", "branch", "-a"], cwd=repo_path)
                if f"remotes/origin/{ref}" in branches or f"{ref}" in branches:
                    ref_type = "branch"
                else:
                    tags = _run_git_command(["git", "tag"], cwd=repo_path).splitlines()
                    if ref in tags:
                        ref_type = "tag"
                    else:
                        try:
                            _run_git_command(["git", "cat-file", "-t", ref], cwd=repo_path)
                            ref_type = "commit"
                        except subprocess.CalledProcessError:
                            ref_type = "unknown"
            except Exception:
                pass

            emoji = {"branch": "🌿", "tag": "🔖", "commit": "💾"}.get(ref_type, "❓")
            logger.info(f"{emoji} Detected ref type: {ref_type}")

            try:
                _run_git_command(["git", "checkout", ref], cwd=repo_path)
            except subprocess.CalledProcessError:
                logger.info(f"⚠️  Direct checkout failed; fetching ref '{ref}' explicitly ...")
                _run_git_command(["git", "fetch", "origin", ref], cwd=repo_path)
                _run_git_command(["git", "checkout", ref], cwd=repo_path)

            checked_commit = _run_git_command(["git", "rev-parse", "HEAD"], cwd=repo_path)
            logger.info(f"✅ Checked out '{repo_name}' to {emoji} '{ref}' ({checked_commit[:10]})")

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to checkout ref '{ref}' for '{repo_name}': {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during checkout of '{repo_name}': {e}")

    def _checkout_to_default_head(repo_name, repo_path, logger):
        """Ensure repo is checked out to the default remote HEAD (usually main/master)."""
        try:
            remote_default = _run_git_command(
                ["git", "symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_path
            )
            default_branch = remote_default.split("/")[-1]
            logger.info(f"🌿 Default branch for '{repo_name}' is '{default_branch}'")

            _run_git_command(["git", "checkout", default_branch], cwd=repo_path)
            _run_git_command(["git", "pull"], cwd=repo_path)

            head_commit = _run_git_command(["git", "rev-parse", "HEAD"], cwd=repo_path)
            logger.info(f"✅ '{repo_name}' is now on '{default_branch}' @ {head_commit[:10]}")

        except subprocess.CalledProcessError as e:
            logger.warning(f"Failed to checkout to default HEAD for '{repo_name}': {e}")
        except Exception as e:
            logger.warning(f"Unexpected error during default head checkout for '{repo_name}': {e}")

    # ---------------- main logic ---------------- #

    for item in paths:
        repo_name, ref = _parse_repo_spec(item)

        # ⭐ Resolve potential local path relative to the CALLER's file
        repo_path = _resolve_from_caller(repo_name)

        if repo_name in sys.modules:
            logger.info(f"🧩 Module '{repo_name}' already loaded — skipping repository and import.")
            continue

        if not repo_path.exists():
            logger.info(f"Repository path not found relative to caller: {repo_name}. Attempting clone...")
            cloned = _try_clone_repo(repo_name, ref)
            if cloned is None or not cloned.exists():
                logger.error(f"Path not found and cloning failed: {repo_name}")
                raise FileNotFoundError(f"Path not found and cloning failed: {repo_name}")
            repo_path = cloned
        else:
            logger.info(f"📁 Repository '{repo_name}' found at {repo_path}")

        if repo_path in seen_paths:
            logger.info(f"ℹ️  Repository '{repo_name}' already processed — skipping.")
            continue
        seen_paths.add(repo_path)

        # Collect .py files
        if repo_path.is_file() and repo_path.suffix == ".py":
            py_files.append(repo_path)
        elif repo_path.is_dir():
            for f in repo_path.rglob("*.py"):
                if "__pycache__" not in f.parts:
                    py_files.append(f)
        else:
            logger.error(f"Invalid path type: {repo_path}")
            raise ValueError(f"Invalid path: {repo_path}")

    # ---------------- import phase ---------------- #

    for file_path in py_files:
        module_name = _compute_module_name(file_path)
        if module_name in sys.modules:
            logger.warning(f"Module already loaded: {module_name} — skipping import.")
            continue

        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            sys.modules[module_name] = module
            caller_globals = inspect.currentframe().f_back.f_globals
            caller_globals[module_name] = module
            imported_modules.append(module_name)
            logger.info(f"✅ Imported module: {module_name} ({file_path})")
        except Exception as e:
            logger.error(f"❌ Failed to import {file_path}: {e}", exc_info=True)

    logger.info(f"📦 Successfully loaded {len(imported_modules)} module(s): {', '.join(imported_modules)}")
    return imported_modules



