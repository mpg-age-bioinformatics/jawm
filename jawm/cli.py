import argparse
import runpy
import sys
import os
import logging


def main():

    # --- Parse CLI arguments ---
    parser = argparse.ArgumentParser(description="JAWM - Just Another Workflow Manager")
    parser.add_argument("workflow", nargs="?", default=".", help="Path to a jawm Python script or directory containing the jawm workflow script with single .py or main.py (default: current directory)")
    parser.add_argument("-p", "--parameters", default=None, help="YAML file(s) or directory of parameter config files to be used as defaults param_file.")
    parser.add_argument("-v", "--variables", default=None, help="YAML or .rc file(s) or directory of files of script variables to inject into the workflow script.")

    args = parser.parse_args()
    
    # --- Setup JAWM-style logging ---
    workflow_label = os.path.basename(os.path.abspath(args.workflow)).replace(".py", "")
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] - %(levelname)s - %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logger = logging.getLogger(f"jawm.cli|{workflow_label}")

    logger.info(f"Initiating JAWM workflow script from jawm command")

    # --- Import Process and preload parameters ---
    from jawm import Process
    if args.parameters:
        Process.set_default(param_file=args.parameters)
        logger.info(f"Loaded parameter file(s): {args.parameters}")

    # --- Prepare variable injection namespace ---
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

    # --- Resolve workflow path (file or folder) ---
    source_path = os.path.abspath(args.workflow)

    if os.path.isfile(source_path) and source_path.endswith(".py"):
        workflow_path = source_path

    elif os.path.isdir(source_path):
        py_files = [f for f in os.listdir(source_path) if f.endswith(".py")]
        if "jawm.py" in py_files:
            workflow_path = os.path.join(source_path, "main.py")
        elif "main.py" in py_files:
            workflow_path = os.path.join(source_path, "main.py")
        elif len(py_files) == 1:
            workflow_path = os.path.join(source_path, py_files[0])
        else:
            logger.error(f"Directory {source_path} must contain at least one .py or jawm.py or main.py file")
            sys.exit(1)

    else:
        logger.error(f"Invalid workflow path: {source_path}")
        sys.exit(1)

    # --- Run the workflow script ---
    try:
        logger.info(f"Running workflow: {workflow_path}")
        runpy.run_path(workflow_path, run_name="__main__", init_globals=exec_namespace)
    except Exception as e:
        logger.error(f"Failed to execute jawm script:\n{e}")
        sys.exit(1)

    logger.info(f"Ending JAWM workflow script from jawm command")