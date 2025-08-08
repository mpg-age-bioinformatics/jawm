import argparse
import runpy
import sys
import os
import logging
import datetime
import contextlib


def main():
    # --- Parse CLI arguments ---
    parser = argparse.ArgumentParser(description="JAWM - Just Another Workflow Manager")
    parser.add_argument("workflow", nargs="?", default=".", help="Path to a jawm Python script or directory containing the jawm workflow script with single .py or main.py (default: current directory)")
    parser.add_argument("-p", "--parameters", default=None, help="YAML file(s) or directory of parameter config files to be used as default param_file.")
    parser.add_argument("-v", "--variables", default=None, help="YAML or .rc file(s) or directory of files of script variables to inject into the workflow script.")
    parser.add_argument("-l", "--logs_directory", default=None, help="Directory to store logs; sets default logs_directory. CLI logs are saved in <logs_directory>/jawm_cli_runs (default: ./logs/jawm_cli_runs).")
    parser.add_argument("-r", "--resume", default=None, help="Resume mode: skip executing already successfully completed processes.")
    parser.add_argument("--no_override", nargs="?", const="ALL", help="Disable override for all or specific parameters (comma-separated).")

    args = parser.parse_args()

    # --- Workflow label and timestamp ---
    workflow_label = os.path.basename(os.path.abspath(args.workflow)).replace(".py", "")
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    # --- CLI log file path ---
    base_logs_dir = os.path.abspath(args.logs_directory) if args.logs_directory else os.path.abspath("./logs")
    run_logs_dir = os.path.join(base_logs_dir, "jawm_cli_runs")
    os.makedirs(run_logs_dir, exist_ok=True)
    cli_log_file = os.path.join(run_logs_dir, f"{workflow_label}_{timestamp}.log")

    # --- Setup logging to terminal and file ---
    log_formatter = logging.Formatter("[%(asctime)s] - %(levelname)s - %(name)s :: %(message)s", "%Y-%m-%d %H:%M:%S")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    # Terminal output
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    # Log file output
    file_handler = logging.FileHandler(cli_log_file, mode="w")
    file_handler.setFormatter(log_formatter)
    root_logger.addHandler(file_handler)

    # CLI logger
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
    if args.resume:
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
            sys.exit(1)

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
            sys.exit(1)
    else:
        logger.error(f"Invalid workflow path: {source_path}")
        sys.exit(1)

    # --- Run the workflow script ---
    try:
        logger.info(f"Running workflow: {workflow_path}")
        runpy.run_path(workflow_path, run_name="__main__", init_globals=exec_namespace)
    except Exception as e:
        logger.error(f"Failed to execute workflow script:\n{e}")
        sys.exit(1)

    logger.info("Ending JAWM workflow script from jawm command")

