import argparse
import runpy
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="JAWM - Just Another Workflow Manager")

    # Flexible workflow source (script or folder)
    parser.add_argument("workflow", nargs="?", default=".", help="Path to a jawm Python script or directory containing the jawm workflow script with single .py or main.py (default: current directory)")
    parser.add_argument("-p", "--parameters", default=None, help="YAML file(s) or directory of parameter config files to be used as defaults param_file.")
    parser.add_argument("-v", "--variables", default=None, help="YAML or .rc file(s) or directory of files of script variables to inject into the workflow script.")

    args = parser.parse_args()

    # Import core class and preload parameters
    from jawm import Process
    if args.parameters:
        Process.set_default(param_file=args.parameters)

    # Prepare variable injection namespace
    exec_namespace = {}
    if args.variables:
        try:
            from jawm._utils import read_variables
            injected_vars = read_variables(args.variables, output_type="dict")
            exec_namespace.update(injected_vars)
            print(f"[JAWM CLI] Injected {len(injected_vars)} variable(s) from {args.variables}")
        except Exception as e:
            print(f"Error: Failed to load variables from {args.variables} — {e}")
            sys.exit(1)

    # Resolve workflow path (script or folder)
    source_path = os.path.abspath(args.workflow)

    if os.path.isfile(source_path) and source_path.endswith(".py"):
        workflow_path = source_path

    elif os.path.isdir(source_path):
        py_files = [f for f in os.listdir(source_path) if f.endswith(".py")]
        if "main.py" in py_files:
            workflow_path = os.path.join(source_path, "main.py")
        elif len(py_files) == 1:
            workflow_path = os.path.join(source_path, py_files[0])
        else:
            print(f"Error: Directory {source_path} must contain only one .py file or a main.py.")
            sys.exit(1)

    else:
        print(f"Error: Invalid workflow path: {source_path}")
        sys.exit(1)

    # Run the resolved script
    try:
        runpy.run_path(workflow_path, run_name="__main__", init_globals=exec_namespace)
    except Exception as e:
        print(f"Failed to execute workflow script:\n{e}")
        sys.exit(1)
