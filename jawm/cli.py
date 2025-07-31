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
    parser.add_argument("-l", "--logs_directory", default=None, help="Directory where CLI run logs will be stored. Defaults to './logs/jawm_runs'.")

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

    # --- Import Process and set defaults ---
    from jawm import Process
    if args.parameters:
        Process.set_default(param_file=args.parameters)
        logger.info(f"Default param_file set to: {args.parameters}")
    if args.logs_directory:
        Process.set_default(logs_directory=args.logs_directory)
        logger.info(f"Default logs_directory set to: {args.logs_directory}")

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

