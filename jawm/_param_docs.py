# jawm/_param_docs.py


PROCESS_PARAM_DOCS = {
    "name": {
        "category": "parameter",
        "description": "Name of the process. Used to identify and track process executions.",
        "type": "str",
        "required": True,
        "example": 'name="my_process"',
        "yaml_example": 'name: "my_process"'
    },
    "param_file": {
        "category": "parameter",
        "description": "YAML file or list of YAML files containing all the possible parameters. Needs to be inputted directly in the Process call. This parameter defines the YAML file(s) the can shape the Process",
        "type": "str or list of str",
        "example": """param_file="parameters/param1.yaml"
# or with multiple files
param_file=["parameters/param1.yaml", "parameters/param2.yaml"]""",
    },
    "script": {
        "category": "parameter",
        "description": "Inline script content to be executed.",
        "type": "str",
        "default": "#!/bin/bash",
        "example": 'script="echo Hello World"',
        "yaml_example": 'script: "echo Hello World"'
    },
    "script_file": {
        "category": "parameter",
        "description": "Path to an external script file to execute.",
        "type": "str",
        "example": 'script_file="scripts/run.sh"',
        "yaml_example": 'script_file: "scripts/run.sh"'
    },
    "script_parameters": {
        "category": "parameter",
        "description": "Dictionary of parameters to substitute into the script.",
        "type": "dict",
        "example": 'script_parameters={"MEM": "4G", "THREADS": "2"}',
        "yaml_example": 'script_parameters: {"MEM": "4G", "THREADS": "2"}'
    },
    "script_parameters_file": {
        "category": "parameter",
        "description": "File containing key=value pairs to use in script placeholder substitution.",
        "type": "str",
        "example": 'script_parameters_file="params.env"',
        "yaml_example": 'script_parameters_file: "params.env"'
    },
    "project_directory": {
        "category": "parameter",
        "description": "Directory for logs, parameters, and outputs.",
        "type": "str",
        "default": ".",
        "example": 'project_directory="/data/project1"',
        "yaml_example": 'project_directory: "/data/project1"'
    },
    "logs_directory": {
        "category": "parameter",
        "description": "Directory to store logs for the process.",
        "type": "str",
        "default": "./logs",
        "example": 'logs_directory="/data/logs"',
        "yaml_example": 'logs_directory: "/data/logs"'
    },
    "parameters_directory": {
        "category": "parameter",
        "description": "Directory where parameter files are saved.",
        "type": "str",
        "example": 'parameters_directory="configs/"',
        "yaml_example": 'parameters_directory: "configs/"'
    },
    "error_summary_file": {
        "category": "parameter",
        "description": "Path to a log file summarizing errors.",
        "type": "str",
        "default": "./logs/error_summary.log",
        "example": 'error_summary_file="logs/errors.log"',
        "yaml_example": 'error_summary_file: "logs/errors.log"'
    },
    "monitoring_directory": {
        "category": "parameter",
        "description": "Directory used for monitoring process status. Can be set via env var JAWM_MONITORING_DIRECTORY.",
        "type": "str",
        "example": 'monitoring_directory="/mnt/monitoring"',
        "yaml_example": 'monitoring_directory: "/mnt/monitoring"'
    },
    "asynchronous": {
        "category": "parameter",
        "description": "Whether the process should run asynchronously.",
        "type": "bool",
        "default": False,
        "example": 'asynchronous=True',
        "yaml_example": 'asynchronous: true'
    },
    "manager": {
        "category": "parameter",
        "description": "Specifies which execution manager to use.",
        "type": "str",
        "default": "metal",
        "allowed": ["metal", "slurm"],
        "example": 'manager="slurm"',
        "yaml_example": 'manager: "slurm"'
    },
    "env": {
        "category": "parameter",
        "description": "Environment variables to set for the process.",
        "type": "dict",
        "example": 'env={"PATH": "/usr/local/bin", "THREADS": "4"}',
        "yaml_example": 'env: {"PATH": "/usr/local/bin", "THREADS": "4"}'
    },
    "inputs": {
        "category": "parameter",
        "description": "Input files or resources required by the process.",
        "type": "dict",
        "example": 'inputs={"input1": "data/input.txt"}',
        "yaml_example": 'inputs: {"input1": "data/input.txt"}'
    },
    "outputs": {
        "category": "parameter",
        "description": "Expected output files or results from the process.",
        "type": "dict",
        "example": 'outputs={"output1": "results/output.txt"}',
        "yaml_example": 'outputs: {"output1": "results/output.txt"}'
    },
    "retries": {
        "category": "parameter",
        "description": "Number of times to retry the process if it fails.",
        "type": "int",
        "default": 0,
        "example": 'retries=2',
        "yaml_example": 'retries: "2"'
    },
    "retry_overrides": {
        "category": "parameter",
        "description": "Dictionary mapping retry index to parameter overrides for that attempt.",
        "type": "dict[int -> dict]",
        "example": 'retry_overrides={1: {"manager": "slurm"}}',
        "yaml_example": 'retry_overrides: {1: {"manager": "slurm"}}'
    },
    "scratch": {
        "category": "parameter",
        "description": "Whether to use scratch space for this process.",
        "type": "bool",
        "default": False,
        "example": 'scratch=True',
        "yaml_example": 'scratch: true'
    },
    "error_strategy": {
        "category": "parameter",
        "description": "Strategy to follow when an error occurs.",
        "type": "str",
        "default": "retry",
        "example": 'error_strategy="fail"',
        "yaml_example": 'error_strategy: "fail"'
    },
    "when": {
        "category": "parameter",
        "description": "Conditional expression or boolean that determines whether to run the process.",
        "type": "bool",
        "default": True,
        "example": 'when=False',
        "yaml_example": 'when: false'
    },
    "before_script": {
        "category": "parameter",
        "description": "Script to execute before the main script.",
        "type": "str",
        "example": 'before_script="echo Preparing..."',
        "yaml_example": 'before_script: "echo Preparing..."'
    },
    "after_script": {
        "category": "parameter",
        "description": "Script to execute after the main script completes.",
        "type": "str",
        "example": 'after_script="echo Done."',
        "yaml_example": 'after_script: "echo Done."'
    },
    "manager_local": {
        "category": "parameter",
        "description": "Local execution manager-specific options.",
        "type": "dict",
        "example": 'manager_local={"threads": 2}',
        "yaml_example": 'manager_local: {"threads": 2}'
    },
    "manager_slurm": {
        "category": "parameter",
        "description": "Slurm manager-specific options (e.g., memory, time).",
        "type": "dict",
        "example": 'manager_slurm={"mem": "4G", "time": "01:00:00"}',
        "yaml_example": 'manager_slurm: {"mem": "4G", "time": "01:00:00"}'
    },
    "environment": {
        "category": "parameter",
        "description": "Execution environment type.",
        "type": "str",
        "default": "local",
        "allowed": ["local", "docker", "apptainer"],
        "example": 'environment="docker"',
        "yaml_example": 'environment: "docker"'
    },
    "container": {
        "category": "parameter",
        "description": "Container image to use for execution.",
        "type": "str",
        "example": 'container="ubuntu:20.04"',
        "yaml_example": 'container: "ubuntu:20.04"'
    },
    "environment_apptainer": {
        "category": "parameter",
        "description": "Options for running the process inside Apptainer.",
        "type": "dict",
        "example": 'environment_apptainer={"bind": ["/data"]}',
        "yaml_example": 'environment_apptainer: {"bind": ["/data"]}'
    },
    "environment_docker": {
        "category": "parameter",
        "description": "Options for running the process inside Docker.",
        "type": "dict",
        "example": 'environment_docker={"cpus": "2"}',
        "yaml_example": 'environment_docker: {"cpus": "2"}'
    }
}
