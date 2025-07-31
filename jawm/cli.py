# jawm/cli.py
import argparse
import runpy
import sys
import os

def main():
    parser = argparse.ArgumentParser(description="JAWM - Just Another Workflow Manager")
    parser.add_argument("workflow_script", help="Path to the Python script defining JAWM workflow.")
    parser.add_argument("-p", "--parameters", help="YAML file or directory of config files.", default=None)
    parser.add_argument("-v", "--variables", help="YAML or .rc file of script variables.", default=None)

    args = parser.parse_args()

    # Import Process and inject global defaults
    from jawm import Process
    if args.parameters:
        Process.set_default(param_file=args.parameters)

    # Load and inject variables into exec_namespace
    exec_namespace = {}
    if args.variables:
        from jawm._utils import read_variables
        injected_vars = read_variables(args.variables, output_type="dict")
        exec_namespace.update(injected_vars)

    # Check workflow path
    workflow_path = os.path.abspath(args.workflow_script)
    if not os.path.isfile(workflow_path):
        print(f"Error: Workflow file not found: {workflow_path}")
        sys.exit(1)

    # Run workflow script
    try:
        runpy.run_path(workflow_path, run_name="__main__", init_globals=exec_namespace)
    except Exception as e:
        print(f"Failed to execute workflow script:\n{e}")
        sys.exit(1)
