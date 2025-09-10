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
    parser.add_argument("-p", "--parameters", default=None, help="YAML file(s) or directory of parameter config files to be used as default param_file.")
    parser.add_argument("-v", "--variables", default=None, help="YAML or .rc file(s) or directory of files of script variables to inject into the workflow script.")
    parser.add_argument("-l", "--logs_directory", "--logs-directory", dest="logs_directory", default=None, help="Directory to store logs; sets default logs_directory. CLI logs are saved in <logs_directory>/jawm_cli_runs (default: ./logs/jawm_cli_runs).")
    parser.add_argument("-r", "--resume", action="store_true", default=None, help="Resume mode: skip executing already successfully completed processes.")
    parser.add_argument("-n", "--no_override", "--no-override", dest="no_override", nargs="?", const="ALL", help="Disable override for all or specific parameters (comma-separated).")
    parser.add_argument("--hash", nargs="?", const="auto", help="Post-run hashing. No value for default hashing or pass a YAML file that lists include paths/globs for content hashing.")
    parser.add_argument("-V", "--version", action="version", version=f"JAWM {_VERSION}")


    args = parser.parse_args()

    # --- Workflow label and timestamp ---
    workflow_label = os.path.basename(os.path.abspath(args.workflow)).replace(".py", "")
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    # --- CLI log file path ---
    base_logs_dir = os.path.abspath(args.logs_directory) if args.logs_directory else os.path.abspath("./logs")
    run_logs_dir = os.path.join(base_logs_dir, "jawm_cli_runs")
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
            logger.info(f"Injected {len(injected_vars)} variable(s) from: {args.variables}")
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
    def _collect_paths_from_yaml_cli(yaml_path):
        """
        Minimal YAML reader to collect include paths/globs for hashing.
        Schema:
        include: [files/dirs/globs]   # required
        exclude_dirs: [dir name patterns]         # optional (not applied here; we let hash_content handle)
        exclude_files: [file name patterns]       # optional (not applied here; we let hash_content handle)
        allowed_extensions: [ext without dot]     # optional
        recursive: true|false                     # optional
        Returns a dict with the resolved 'paths' and optional policy keys.
        """
        data = yaml.safe_load(Path(yaml_path).read_text()) or {}
        include = data.get("include")
        if not include:
            return {"paths": []}
        if isinstance(include, str):
            include = [include]

        # expand globs; keep literal if no match
        expanded, seen = [], set()
        for pat in include:
            hits = glob.glob(pat, recursive=True) or [pat]
            for h in hits:
                if h not in seen:
                    expanded.append(h); seen.add(h)

        return {
            "paths": expanded,
            "allowed_extensions": data.get("allowed_extensions"),
            "exclude_dirs": data.get("exclude_dirs"),
            "exclude_files": data.get("exclude_files"),
            "recursive": data.get("recursive", True),
        }


    def _default_hash_output_path_cli(logs_dir: str, workflow_path: str):
        """
        Default hash file under <logs_dir>/jawm_cli_hashes/<workflow_stem>.hash
        (single canonical location to compare runs).
        """
        wf_stem = os.path.splitext(os.path.basename(workflow_path))[0]
        out_dir = os.path.join(os.path.abspath(logs_dir), "jawm_cli_hashes")
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, f"{wf_stem}.hash")


    def _write_and_compare_hash_cli(hash_value: str, out_path: str):
        """
        Compare with existing file (if any), print a clear log, and write the new hash.
        Returns True if written or matched, False if mismatch (but still writes).
        """
        outp = Path(out_path)
        outp.parent.mkdir(parents=True, exist_ok=True)
        matched = True
        if outp.exists():
            stored = outp.read_text().strip()
            if stored != hash_value:
                matched = False
                # Required: log mismatch to CLI output
                logger.warning(f"[hash] mismatch for {outp.name}: \nStored={stored} \nComputed={hash_value}")
            else:
                logger.info(f"[hash] matches existing file {outp.name}")
        outp.write_text(hash_value + "\n")
        logger.info(f"[hash] wrote hash to: {outp}")
        return matched


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
    try:
        logger.info(f"Running workflow: {workflow_path}")
        try:
            runpy.run_path(workflow_path, run_name="__main__", init_globals=exec_namespace)
        except SystemExit as e:
            # Defer exiting until after we perform cleanup + hashing
            exit_code_from_script = e.code if isinstance(e.code, int) else 0
            logger.info(f"Workflow ended with exitcode ({exit_code_from_script}); Initiating post run procedures.")


        # Wait for process to fully end and cleaned up
        deadline = time.time() + 120
        while Process.list_monitoring_threads():
            if time.time() >= deadline:
                logger.warning("Timed out after 2 minutes waiting for processes to finish/clean up; CLOSING ANYWAY!")
                break
            time.sleep(1)

        # -------- post-run hashing (always reached, even if workflow sys.exit'ed) --------
        if args.hash is not None:
            from jawm._utils import hash_content  # canonical hasher

            # Use the actually-resolved script we executed (jawm.py/main.py/<only>.py)
            resolved_workflow_path = workflow_path
            logs_dir = os.path.abspath(args.logs_directory) if args.logs_directory else os.path.abspath("./logs")
            out_path = _default_hash_output_path_cli(logs_dir, resolved_workflow_path)

            logger.info(f"[hash] mode={args.hash!r} -> output file: {out_path}")

            if args.hash == "auto" or args.hash is None:
                combined_hash = _compute_run_hash_from_process_prefixes_cli()

                if not combined_hash:
                    inputs = [resolved_workflow_path]
                    if args.parameters:
                        inputs.append(os.path.abspath(args.parameters))
                    if args.variables:
                        inputs.append(os.path.abspath(args.variables))

                    if inputs:
                        combined_hash = hash_content(
                            inputs,
                            allowed_extensions=None,
                            exclude_dirs=[".git", "__pycache__", ".mypy_cache", ".ipynb_checkpoints"],
                            exclude_files=["*.tmp", "*.swp"],
                            recursive=True,
                        )
                    else:
                        combined_hash = hashlib.sha256(b"").hexdigest()

                logger.info(f"[hash] hash for the current run: {combined_hash}")
                _write_and_compare_hash_cli(combined_hash, out_path)

            else:
                cfg = _collect_paths_from_yaml_cli(os.path.abspath(args.hash))
                paths = cfg.get("paths") or []
                if not paths:
                    logger.warning("[hash] YAML produced no paths to hash")
                    combined_hash = hashlib.sha256(b"").hexdigest()
                else:
                    combined_hash = hash_content(
                        paths,
                        allowed_extensions=cfg.get("allowed_extensions"),
                        exclude_dirs=cfg.get("exclude_dirs"),
                        exclude_files=cfg.get("exclude_files"),
                        recursive=cfg.get("recursive", True),
                    )
                logger.info(f"JAWM hash: {combined_hash}")
                _write_and_compare_hash_cli(combined_hash, out_path)

    except Exception:
        logger.exception("Failed to execute workflow script")
        # If workflow raised SystemExit, prefer that code; else generic failure
        sys.exit(exit_code_from_script if exit_code_from_script is not None else 1)
    finally:
        code = 0 if exit_code_from_script is None else exit_code_from_script
        if code == 0:
            logger.info("Ending JAWM workflow script from jawm command")
        else:
            logger.error(f"Ending JAWM workflow script from jawm command with exit code {code}")
        # Now, if the script wanted to exit with a specific code, honor it
        if exit_code_from_script is not None:
            sys.exit(exit_code_from_script)
