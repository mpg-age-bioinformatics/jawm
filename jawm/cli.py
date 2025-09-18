import argparse
import runpy
import sys
import os
import glob
import hashlib
import logging
import datetime
import io
import atexit
import threading
import time
import yaml
import fnmatch
from pathlib import Path


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


def _start_global_tee(path, mode="a"):
    """
    Mirror everything written to sys.stdout and sys.stderr to the given file,
    while still showing it on the real terminal. Lives until process exit.
    """
    f = open(path, mode, buffering=1, encoding="utf-8")  # line-buffered

    class _Tee(io.TextIOBase):
        def __init__(self, stream, file_obj, lock=None):
            self.stream = stream
            self.file = file_obj
            self.lock = lock or threading.Lock()
        def write(self, data):
            # write to both console and file atomically to preserve ordering
            with self.lock:
                self.stream.write(data)
                self.stream.flush()
                self.file.write(data)
                self.file.flush()
            return len(data)
        def flush(self):
            with self.lock:
                self.stream.flush()
                self.file.flush()
        def isatty(self):
            # preserve TTY semantics for libraries that check this
            return getattr(self.stream, "isatty", lambda: False)()

        def writable(self):
            return True

        def fileno(self):
            # some libs probe fileno(); prefer the real stream,
            # fall back to the logfile if needed
            try:
                return self.stream.fileno()
            except Exception:
                return self.file.fileno()

    lock = threading.Lock()
    # Redirect program-visible stdio to Tee that writes to the real console and the file
    sys.stdout = _Tee(sys.__stdout__, f, lock)
    sys.stderr = _Tee(sys.__stderr__, f, lock)

    # Make sure unhandled exceptions in threads are printed to stderr (captured by tee)
    def _thread_excepthook(args):
        import traceback
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
    threading.excepthook = _thread_excepthook

    @atexit.register
    def _cleanup():
        # flush & restore real stdio so other atexit handlers behave
        try:
            sys.stdout.flush(); sys.stderr.flush()
        finally:
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            f.close()


def main():
    # --- Parse CLI arguments ---
    parser = argparse.ArgumentParser(description="JAWM - Just Another Workflow Manager")
    parser.add_argument("workflow", nargs="?", default=".", help="Path to a jawm Python script or directory containing the jawm workflow script with single .py or main.py (default: current directory)")
    parser.add_argument("-p", "--parameters", nargs="+", default=None, help="YAML file(s) or directory of parameter config files to be used as default param_file.")
    parser.add_argument("-v", "--variables", nargs="+", default=None, help="YAML or .rc file(s) or directory of files of script variables to inject into the workflow script.")
    parser.add_argument("-l", "--logs_directory", "--logs-directory", dest="logs_directory", default=None, help="Directory to store logs; sets default logs_directory. CLI logs are saved in <logs_directory>/jawm_runs (default: ./logs/jawm_runs).")
    parser.add_argument("-r", "--resume", action="store_true", default=None, help="Resume mode: skip executing already successfully completed processes.")
    parser.add_argument("-n", "--no_override", "--no-override", dest="no_override", nargs="?", const="ALL", help="Disable override for all or specific parameters (comma-separated).")
    parser.add_argument("-V", "--version", action="version", version=f"JAWM {_VERSION}")


    args = parser.parse_args()

    # normalize -p and -v: single item → string; many → list
    if args.parameters is not None and isinstance(args.parameters, list) and len(args.parameters) == 1:
        args.parameters = args.parameters[0]
    if args.variables is not None and isinstance(args.variables, list) and len(args.variables) == 1:
        args.variables = args.variables[0]

    # --- Workflow label and timestamp ---
    workflow_label = os.path.basename(os.path.abspath(args.workflow)).replace(".py", "")
    now = datetime.datetime.now()
    timestamp = now.strftime('%Y%m%d_%H%M%S')
    timestamp_iso = now.strftime("%Y-%m-%dT%H:%M:%S")

    # --- CLI log file path ---
    base_logs_dir = os.path.abspath(args.logs_directory) if args.logs_directory else os.path.abspath("./logs")
    run_logs_dir = os.path.join(base_logs_dir, "jawm_runs")
    os.makedirs(run_logs_dir, exist_ok=True)
    cli_log_file = os.path.join(run_logs_dir, f"{workflow_label}_{timestamp}.log")

    # --- Start global tee BEFORE any prints/logging so we catch everything ---
    _start_global_tee(cli_log_file, mode="w")

    # --- Configure logging: stream ONLY (to sys.stdout which is tee'd), no FileHandler needed ---
    log_formatter = logging.Formatter(
        "[%(asctime)s] - %(levelname)s - %(name)s :: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)  # goes through tee
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    logger = logging.getLogger(f"jawm.cli|{workflow_label}")
    logger.info("Initiating JAWM workflow script from jawm command")
    logger.info(f"Logging terminal output to: {cli_log_file}")

    # --- Import Process and set defaults or overrides ---
    from jawm import Process

    no_override_params = (
        ["ALL"] if args.no_override and args.no_override.strip().upper() == "ALL"
        else [p.strip() for p in args.no_override.split(",") if p.strip()] if args.no_override else []
    )

    def _apply_param(key, value):
        """Helper to decide whether to use set_default or set_override."""
        if "ALL" in no_override_params or key in no_override_params:
            Process.set_default(**{key: value})
            logger.info(f"Default {key} set to: {value}")
        else:
            Process.set_override(**{key: value})
            logger.info(f"Override {key} set to: {value}")

    if args.parameters:
        _apply_param("param_file", args.parameters)
    if args.logs_directory:
        _apply_param("logs_directory", args.logs_directory)
    if args.resume is not None:
        _apply_param("resume", True)

    # --- Load and inject variables into script namespace ---
    exec_namespace = {}
    if args.variables:
        try:
            from jawm._utils import read_variables
            injected_vars = read_variables(args.variables, output_type="dict")
            exec_namespace.update(injected_vars)
            logger.info(f"Injected {len(injected_vars)} variable(s) from: {args.variables} to the script")
            _apply_param("var_file", args.variables)
        except Exception as e:
            logger.error(f"Failed to load variables from {args.variables} — {e}")
            sys.exit(2)

    # --- Resolve workflow path ---
    source_path = os.path.abspath(args.workflow)
    if os.path.isfile(source_path) and source_path.endswith(".py"):
        workflow_path = source_path
    elif os.path.isdir(source_path):
        py_files = [f for f in os.listdir(source_path) if f.endswith(".py")]
        if "jawm.py" in py_files:
            workflow_path = os.path.join(source_path, "jawm.py")
        elif "main.py" in py_files:
            workflow_path = os.path.join(source_path, "main.py")
        elif len(py_files) == 1:
            workflow_path = os.path.join(source_path, py_files[0])
        else:
            logger.error(f"Directory {source_path} must contain only one .py file or a main.py")
            sys.exit(2)
    else:
        logger.error(f"Invalid workflow path: {source_path}")
        sys.exit(2)

    # --- INTERNAL HELPERS FOR HASHING (CLI-ONLY) ---
    # distinct exit code so callers/CI can detect reference mismatches
    EXIT_HASH_REFERENCE_MISMATCH = 73
    
        
    def _collect_hash_cfg_from_param_sources_cli(param_sources):
        """
        Look through param file(s)/dir for entries with `scope: hash`
        and merge them into a single cfg.

        Returns a dict like:
        {
            "paths": [...],                # from `include` entries (glob/literal)
            "allowed_extensions": [...],   # or None
            "exclude_dirs": [...],         # or None
            "exclude_files": [...],        # or None
            "recursive": True/False,
            "overwrite": True/False,
            "reference": hash string/path
        }
        or {} if nothing found.
        """
        def _as_list(x):
            if not x: return []
            return x if isinstance(x, list) else [x]

        # Gather YAML files from -p (file/dir/list)
        yaml_files = []
        if not param_sources:
            return {}
        sources = param_sources if isinstance(param_sources, list) else [param_sources]
        for src in sources:
            src = os.path.abspath(str(src))
            if os.path.isdir(src):
                for f in os.listdir(src):
                    if f.lower().endswith((".yaml", ".yml")):
                        yaml_files.append(os.path.join(src, f))
            elif os.path.isfile(src) and src.lower().endswith((".yaml", ".yml")):
                yaml_files.append(src)

        if not yaml_files:
            return {}

        # Merge all scope: hash entries
        merged = {
            "include": [],
            "allowed_extensions": None,
            "exclude_dirs": None,
            "exclude_files": None,
            "recursive": True,
            "overwrite": False,
            "reference": None
        }

        def _merge_list_field(key, new_val):
            if new_val is None:
                return
            existing = merged.get(key)
            if existing is None:
                merged[key] = _as_list(new_val)
            else:
                merged[key] = _as_list(existing) + _as_list(new_val)

        def _take_last_scalar(key, new_val):
            if new_val is not None:
                merged[key] = new_val

        for yf in yaml_files:
            try:
                data = yaml.safe_load(Path(yf).read_text()) or []
            except Exception:
                continue
            # Allow either a single dict or a list of dicts
            docs = data if isinstance(data, list) else [data]
            for entry in docs:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("scope", "")).lower() != "hash":
                    continue
                # same schema as --hash YAML
                _merge_list_field("include", entry.get("include"))
                _take_last_scalar("allowed_extensions", entry.get("allowed_extensions"))
                _take_last_scalar("exclude_dirs", entry.get("exclude_dirs"))
                _take_last_scalar("exclude_files", entry.get("exclude_files"))
                _take_last_scalar("recursive", entry.get("recursive"))
                _take_last_scalar("overwrite", entry.get("overwrite"))
                _take_last_scalar("reference", entry.get("reference"))

        if not merged["include"]:
            return {}

        # Expand globs
        expanded, seen = [], set()
        for pat in _as_list(merged["include"]):
            hits = glob.glob(pat, recursive=True) or [pat]
            for h in hits:
                if h not in seen:
                    expanded.append(h); seen.add(h)

        return {
            "paths": expanded,
            "allowed_extensions": merged["allowed_extensions"],
            "exclude_dirs": merged["exclude_dirs"],
            "exclude_files": merged["exclude_files"],
            "recursive": True if merged["recursive"] is None else bool(merged["recursive"]),
            "overwrite": False if merged["overwrite"] is None else bool(merged["overwrite"]),
            "reference": merged.get("reference"),
        }


    def _resolve_reference_hash_cli(ref):
        """
        Resolve a reference to a SHA-256 hex string.
        - If 'ref' is a readable file path, read its first non-empty line.
        - Else, treat 'ref' as a literal hash string.
        Returns a normalized lowercase hex string, or None if invalid.
        """
        candidate = None
        try:
            if isinstance(ref, str) and os.path.isfile(ref):
                txt = Path(ref).read_text(encoding="utf-8", errors="ignore")
                for line in txt.splitlines():
                    line = line.strip()
                    if line:
                        candidate = line
                        break
            else:
                candidate = str(ref).strip()
        except Exception:
            return None

        if not candidate:
            return None

        h = candidate.lower().strip()
        # allow optional "sha256:" prefix
        if h.startswith("sha256:"):
            h = h.split(":", 1)[1].strip()

        # minimal validation for sha256
        import re
        if re.fullmatch(r"[0-9a-f]{64}", h):
            return h
        return None
    
    def _enumerate_hash_inputs_cli(paths, *, allowed_extensions=None, exclude_dirs=None, exclude_files=None, recursive=True):
        """
        Return a sorted list of concrete files that would be considered for hashing,
        using the same policy (ext filter, exclude lists, recursion) as hash_content.
        """
        if paths is None:
            return []
        if isinstance(paths, (str, Path)):
            paths = [paths]

        allowed_exts = None
        if allowed_extensions:
            allowed_exts = set(("." + e.lower().lstrip(".")) for e in allowed_extensions)

        exclude_dirs = exclude_dirs or []
        exclude_files = exclude_files or []

        collected = []

        def _file_ok(fname):
            base = os.path.basename(fname)
            if any(fnmatch.fnmatch(base, pat) for pat in exclude_files):
                return False
            if allowed_exts is not None:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in allowed_exts:
                    return False
            return True

        for p in paths:
            p = os.path.abspath(str(p))
            if os.path.isfile(p):
                if _file_ok(p):
                    collected.append(p)
            elif os.path.isdir(p):
                if recursive:
                    for root, dirs, files in os.walk(p):
                        # apply dir excludes (by name pattern)
                        dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, pat) for pat in (exclude_dirs or []))]
                        for f in files:
                            fp = os.path.join(root, f)
                            if _file_ok(fp):
                                collected.append(fp)
                else:
                    for f in os.listdir(p):
                        fp = os.path.join(p, f)
                        if os.path.isfile(fp) and _file_ok(fp):
                            collected.append(fp)
            else:
                # ignore non-existent, same as the hasher
                continue

        return sorted(set(collected))


    def _default_hash_output_path_cli(logs_dir, workflow_path):
        """
        Default hash file under <logs_dir>/jawm_hashes/<workflow_stem>.hash
        (single canonical location to compare runs).
        """
        wf_stem = os.path.splitext(os.path.basename(workflow_path))[0]
        out_dir = os.path.join(os.path.abspath(logs_dir), "jawm_hashes")
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, f"{wf_stem}.hash")
    

    def _input_history_path_cli(logs_dir, workflow_path):
        """
        Always-written auto history:
        <logs_dir>/jawm_hashes/<workflow>_input.history
        """
        wf_stem = os.path.splitext(os.path.basename(workflow_path))[0]
        out_dir = os.path.join(os.path.abspath(logs_dir), "jawm_hashes")
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, f"{wf_stem}_input.history")


    def _user_defined_history_path_cli(logs_dir, workflow_path):
        """
        Written only when -p contains `scope: hash`:
        <logs_dir>/jawm_hashes/<workflow>_user_defined.history
        """
        wf_stem = os.path.splitext(os.path.basename(workflow_path))[0]
        out_dir = os.path.join(os.path.abspath(logs_dir), "jawm_hashes")
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, f"{wf_stem}_user_defined.history")
    

    def _append_history_line_cli(history_path, ts, hash_value, log_file, files_csv="-", user_provided=False):
        """
        Append: "<timestamp>\t<hash>\t<cli_log_file>\t<comma_separated_files>"
        to the given history file path.
        """
        Path(history_path).parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(f"{ts}\t{hash_value}\t{log_file}\t{files_csv}\n")
        if user_provided:
            logger.info(f"[hash] Appended history based on user definitions → {history_path}")


    def _write_and_compare_hash_cli(hash_value, out_path, overwrite=False):
        """
        Compare with existing file (if any), print a clear log, and write the new hash.
        Returns True if written or matched, False if mismatch (but still writes).
        """
        outp = Path(out_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        matched = True
        new = True
        if outp.exists():
            stored = outp.read_text().strip()
            new = False
            if stored != hash_value:
                matched = False
                # Required: log mismatch to CLI output
                logger.warning(f"[hash] Mismatch for {outp.name}: \nStored={stored} \nComputed={hash_value}")
            else:
                logger.info(f"[hash] Matches existing file {outp.name}")
        if not outp.exists() or overwrite:
            outp.write_text(hash_value + "\n")
            logger.info(f"[hash] Wrote current hash to: {outp}")
        return matched, new


    def _compute_run_hash_from_process_prefixes_cli():
        """
        Default/auto mode: use the first 6 chars of *executed* Processes' hashes.

        We read them via the public API to avoid reaching into internals.
        Deterministic: sort prefixes; hash the concatenated string.
        """
        try:
            from jawm import Process
        except Exception:
            return None  # jawm not available; likely shouldn't happen

        items = Process.list_all()  # [{name, hash, log_path, finished, ...}, ...]
        prefixes = []
        for p in items:
            h = p.get("hash")
            # consider "executed" as those that have an execution_start timestamp
            if not h:
                continue
            # keep those that actually ran (have an exit code OR are marked finished)
            # This still includes successful/failed/skipped, which is fine for a run signature.
            prefixes.append(str(h)[:6])

        if not prefixes:
            return None

        prefixes = sorted(set(prefixes))
        payload = "\n".join(prefixes).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


    # --- Run the workflow script ---
    exit_code_from_script = None
    exit_code_def = 0
    try:
        logger.info(f"Running workflow: {workflow_path}")
        try:
            runpy.run_path(workflow_path, run_name="__main__", init_globals=exec_namespace)
        except SystemExit as e:
            # Defer exiting until after we perform cleanup + hashing
            exit_code_from_script = e.code if isinstance(e.code, int) else 0
            logger.info(f"Workflow ended with exitcode ({exit_code_from_script}); Initiating post run procedures.")

        exit_code_def = 0 if exit_code_from_script is None else exit_code_from_script


        # Wait for process to fully end and cleaned up
        deadline = time.time() + 120
        while Process.list_monitoring_threads():
            if time.time() >= deadline:
                logger.warning("Timed out after 2 minutes waiting for processes to finish/clean up; CLOSING ANYWAY!")
                break
            time.sleep(1)

        # -------- post-run hashing & histories (always reached, even if workflow sys.exit'ed) --------
        from jawm._utils import hash_content  # canonical hasher

        def _extend_inputs_from_arg(val):
            if not val:
                return []
            if isinstance(val, list):
                return [os.path.abspath(v) for v in val]
            return [os.path.abspath(val)]

        resolved_workflow_path = workflow_path
        logs_dir = os.path.abspath(args.logs_directory) if args.logs_directory else os.path.abspath("./logs")

        # === Always write AUTO INPUT HISTORY ====
        # hash value: prefix-hash if available, else file-content hash on fallback.
        # files list: enumerate workflow + -p + -v (even if prefix-mode succeeds).
        auto_files_csv = "-"
        auto_history_path = _input_history_path_cli(logs_dir, resolved_workflow_path)

        # enumerate candidate inputs (for history files list)
        auto_inputs = [resolved_workflow_path]
        auto_inputs += _extend_inputs_from_arg(args.parameters)
        auto_inputs += _extend_inputs_from_arg(args.variables)
        auto_files_considered = _enumerate_hash_inputs_cli(
            auto_inputs,
            allowed_extensions=None,
            exclude_dirs=[".git", "__pycache__", ".mypy_cache", ".ipynb_checkpoints"],
            exclude_files=["*.tmp", "*.swp"],
            recursive=True,
        )
        if auto_files_considered:
            auto_files_csv = ",".join(auto_files_considered)

        # compute auto hash (prefix-mode preferred)
        auto_hash = _compute_run_hash_from_process_prefixes_cli()
        if not auto_hash:
            if auto_inputs:
                auto_hash = hash_content(
                    auto_inputs,
                    allowed_extensions=None,
                    exclude_dirs=[".git", "__pycache__", ".mypy_cache", ".ipynb_checkpoints"],
                    exclude_files=["*.tmp", "*.swp"],
                    recursive=True,
                )
            else:
                auto_hash = hashlib.sha256(b"").hexdigest()

        # append to <wf>_input.history
        _append_history_line_cli(
            history_path=auto_history_path,
            ts=timestamp_iso,
            hash_value=auto_hash,
            log_file=cli_log_file,
            files_csv=auto_files_csv,
        )

        # === Optional USER-DEFINED HASH from -p (scope: hash) ====
        # If present: compute content hash using that policy, write <wf>.hash, and append <wf>_user_defined.history
        param_hash_cfg = {}
        try:
            param_hash_cfg = _collect_hash_cfg_from_param_sources_cli(args.parameters)
        except Exception as e:
            logger.warning(f"[hash] Failed to read scope: hash from param file(s): {e}")
            param_hash_cfg = {}

        if param_hash_cfg:
            cfg = param_hash_cfg
            paths = cfg.get("paths") or []
            overwrite = cfg.get("overwrite", False)
            reference = cfg.get("reference")

            userdef_files_csv = "-"
            if paths:
                userdef_files_considered = _enumerate_hash_inputs_cli(
                    paths,
                    allowed_extensions=cfg.get("allowed_extensions"),
                    exclude_dirs=cfg.get("exclude_dirs"),
                    exclude_files=cfg.get("exclude_files"),
                    recursive=cfg.get("recursive", True),
                )
                if userdef_files_considered:
                    userdef_files_csv = ",".join(userdef_files_considered)

                userdef_hash = hash_content(
                    paths,
                    allowed_extensions=cfg.get("allowed_extensions"),
                    exclude_dirs=cfg.get("exclude_dirs"),
                    exclude_files=cfg.get("exclude_files"),
                    recursive=cfg.get("recursive", True),
                )
            else:
                logger.warning("[hash] No paths found in user hashing definitions")
                userdef_hash = hashlib.sha256(b"").hexdigest()

            # write <wf>.hash (same as before)
            hash_out_path = _default_hash_output_path_cli(logs_dir, resolved_workflow_path)
            logger.info(f"[hash] Generated hash from user definitions → {userdef_hash}")
            matched, new = _write_and_compare_hash_cli(userdef_hash, hash_out_path, overwrite=overwrite)

            # status logging only for user-defined hash
            if matched:
                if new:
                    logger.info("[hash] STATUS: NEW  ✅")
                else:
                    logger.info("[hash] STATUS: MATCHED  ✅")
            else:
                logger.info("[hash] STATUS: MISMATCHED  ❌")

            userdef_history_path = _user_defined_history_path_cli(logs_dir, resolved_workflow_path)
            _append_history_line_cli(
                history_path=userdef_history_path,
                ts=timestamp_iso,
                hash_value=userdef_hash,
                log_file=cli_log_file,
                files_csv=userdef_files_csv,
                user_provided=True
            )

            # Reference check (AFTER history append & status logging)
            if reference:
                expected = _resolve_reference_hash_cli(reference)
                if not expected:
                    logger.error(f"[hash] Invalid reference provided: {reference!r}")
                    sys.exit(EXIT_HASH_REFERENCE_MISMATCH)
                if userdef_hash != expected:
                    logger.error("[hash] ❌  Generated user-defined hash does NOT match reference — aborting with EXITCODE 73  ❌")
                    sys.exit(EXIT_HASH_REFERENCE_MISMATCH)
                else:
                    logger.info("[hash] ✅  Generated user-defined hash matched reference  ✅")

    except Exception:
        logger.exception("Failed to execute workflow script")
        # If workflow raised SystemExit, prefer that code; else generic failure
        sys.exit(exit_code_from_script if exit_code_from_script is not None else 1)
    finally:
        if exit_code_def == 0:
            logger.info("Ending JAWM workflow script from jawm command")
        else:
            logger.error(f"Ending JAWM workflow script from jawm command with exit code {exit_code_def}")
        # Now, if the script wanted to exit with a specific code, honor it
        if exit_code_from_script is not None:
            sys.exit(exit_code_from_script)
