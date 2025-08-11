import argparse
import runpy
import sys
import os
import logging
import datetime
import io
import atexit
import threading

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
    parser.add_argument("-l", "--logs_directory", default=None, help="Directory to store logs; sets default logs_directory. CLI logs are saved in <logs_directory>/jawm_cli_runs (default: ./logs/jawm_cli_runs).")
    parser.add_argument("-r", "--resume", action="store_true", default=None, help="Resume mode: skip executing already successfully completed processes.")
    parser.add_argument("-n", "--no-override", "--no_override", nargs="?", const="ALL", help="Disable override for all or specific parameters (comma-separated).")

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

    # --- Run the workflow script ---
    try:
        logger.info(f"Running workflow: {workflow_path}")
        runpy.run_path(workflow_path, run_name="__main__", init_globals=exec_namespace)
    except Exception as e:
        logger.error(f"Failed to execute workflow script:\n{e}")
        sys.exit(1)
    finally:
        logger.info("Ending JAWM workflow script from jawm command")
