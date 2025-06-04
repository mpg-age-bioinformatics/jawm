# jawm/_param_docs.py


PROCESS_PARAM_DOCS = {
    "name": {
        "category": "parameter",
        "description": "Name of the process. Used to identify and track process executions.",
        "note": "Unique process name is preferred for easier identification and to avoid conflicts.",
        "type": "str",
        "required": True,
        "example": 'name="my_process"',
        "yaml_example": 'name: "my_process"'
    },

    "hash": {
        "category": "parameter",
        "description": "A generated 7 digit hash. Used to identify and track process executions.",
        "note": "Process hash would be generated automatically when a Process initiated. User doesn't need to provide any value.",
        "type": "str",
    },

    "param_file": {
        "category": "parameter",
        "description": "YAML file or list of YAML files containing all the possible parameters.",
        "note": "Needs to be inputted directly in the Process call. This parameter defines the YAML file(s) that can shape the Process.",
        "type": "str or list of str",
        "example": """param_file="parameters/param1.yaml"
# or with multiple files
param_file=["parameters/param1.yaml", "parameters/param2.yaml"]""",
    },

    "script": {
        "category": "parameter",
        "description": "Inline script content to be executed. Inline script would have the higher preference.",
        "note": "Script requires to have a shebang initiation as the first line, such as`#!/bin/bash` or `#!/usr/bin/env python3`.",
        "type": "str",
        "default": "#!/bin/bash",
        "example": """script=\"\"\"#!/usr/bin/env python3
for fruit in ["Apple", "Banana", "Ananas"]:
    print(f"Fruit: {fruit}")
\"\"\"""",
        "yaml_example": """script: |
#!/usr/bin/env python3
for fruit in ["Apple", "Banana", "Ananas"]:
    print(f"Fruit: {fruit}")"""
    },

    "script_file": {
        "category": "parameter",
        "description": "Path to an external script file to execute.",
        "note": "Script file requires to have a shebang initiation as the first line, such as`#!/bin/bash` or `#!/usr/bin/env python3`.",
        "type": "str",
        "example": 'script_file="scripts/run.sh"',
        "yaml_example": 'script_file: "scripts/run.sh"'
    },

    "script_parameters": {
        "category": "parameter",
        "description": "Dictionary of parameters to substitute into the script.",
        "note": "Parameter values will substitute the placeholder(s) in the script. Please be caution as any wrong use of paramters can break the script.",
        "type": "dict",
        "example": """script_parameters={
    "APPNAME": "JAWM",
    "BYEMSG": "GOOD BYE!",
    "FRUITLIST": "['Apple', 'Banana', 'Orange']"
}""",
        "yaml_example": """script_parameters:
    APPNAME: "JAWM"
    BYEMSG: "GOOD BYE!"
    FRUITLIST: "['Apple', 'Banana', 'Orange']"
"""
    },

    "script_parameters_file": {
        "category": "parameter",
        "description": "File containing key = value pairs to use in script placeholder substitution.",
        "note": "Parameter values will substitute the placeholder(s) in the script. Please be caution as any wrong use of paramters can break the script.",
        "type": "str",
        "example": 'script_parameters_file="script/hello.rc"',
        "yaml_example": 'script_parameters_file: "script/hello.rc"'
    },
    "project_directory": {
        "category": "parameter",
        "description": "Directory for logs, parameters, and outputs.",
        "note": "Current direcrtory would be the project directory by default",
        "type": "str",
        "default": ".",
        "example": 'project_directory="/data/project1"',
        "yaml_example": 'project_directory: "/data/project1"'
    },
    "logs_directory": {
        "category": "parameter",
        "description": "Directory to store all the logs for the process.",
        "type": "str",
        "default": "<project_directory>/logs",
        "example": 'logs_directory="/data/logs"',
        "yaml_example": 'logs_directory: "/data/logs"'
    },
    "error_summary_file": {
        "category": "parameter",
        "description": "Path to a log file summarizing all the errors with time records.",
        "note": "This should be the go to file while checking for error logs",
        "type": "str",
        "default": "<logs_directory>/error_summary.log",
        "example": 'error_summary_file="logs/error_summary.log"',
        "yaml_example": 'error_summary_file: "logs/error_summary.log"'
    },
    "monitoring_directory": {
        "category": "parameter",
        "description": "Directory used for monitoring process status. Completed or Running jobs with basic details can be found in this location",
        "note": "Can be set via env var `JAWM_MONITORING_DIRECTORY`.",
        "type": "str",
        "default": "~/.jawm/monitoring",
        "example": 'monitoring_directory="/jawm/monitoring"',
        "yaml_example": 'monitoring_directory: "/jawm/monitoring"'
    },
    "asynchronous": {
        "category": "parameter",
        "description": "Whether the process should run asynchronously.",
        "note": "If asynchronous is True, the process runs in a background thread, allowing the main program to continue without blocking.",
        "type": "bool",
        "default": "False",
        "example": 'asynchronous=True',
        "yaml_example": 'asynchronous: true'
    },
    "manager": {
        "category": "parameter",
        "description": "Specifies which execution manager to use.",
        "type": "str",
        "default": "local",
        "allowed": ["local", "slurm"],
        "example": 'manager="slurm"',
        "yaml_example": 'manager: "slurm"'
    },
    "env": {
        "category": "parameter",
        "description": "Environment variables to set for the process.",
        "type": "dict",
        "example": 'env={"PATH": "/usr/local/bin", "THREADS": "4"}',
        "yaml_example": """env:
    PATH: "/usr/local/bin"
    THREADS: "4"
"""
    },
    "inputs": {
        "category": "parameter",
        "description": "Any extra/custom paramters to use in the Process or Process script can be pushed with inputs.",
        "type": "dict",
        "example": 'inputs={"input1": "data/input.txt"}',
        "yaml_example": 'inputs: {"input1": "data/input.txt"}'
    },
    "outputs": {
        "category": "parameter",
        "description": "Any extra/custom output paramters to use in the Process or Process script can be pushed with inputs.",
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
        "description": "Overrides specific parameters for each retry attempt. Keys represent retry attempt numbers (1-based).",
        "note": "Supports both fixed values and relative updates (e.g., '+2', '+20%') for numeric fields like memory or time. Decimal values like '3.2G' are allowed, but may be rounded by Slurm depending on system configuration.",
        "type": "dict[int -> dict]",
        "example": """retry_overrides={
        1: {"manager_slurm": {"partition": "debug", "mem": "+100%", "time": "+60"}},
        2: {"manager_slurm": {"mem": "3.2G", "time": "00:05:00"}},
        3: {"manager_slurm": {"mem": "+1", "time": "+50%"}}
    }""",
        "yaml_example": """retry_overrides:
    1:
        manager_slurm:
            partition: "debug"
            mem: "+100%"
            time: "+60"
    2:
        manager_slurm:
            mem: "3.2G"
            time: "00:05:00"
    3:
        manager_slurm:
            mem: "+1"
            time: "+50%"
    """
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
        "note": "The `when` parameter can be a boolean or a function returning a boolean. If False, the process will be skipped entirely. Dynamic skipping also possible with like`when=lambda: os.path.exists(\"input.txt\")`",
        "type": "bool",
        "default": "True",
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
    },

    # Examples

    "example_hello_world": {
        "category": "example",
        "description": "Basic Hello World example with default setup.",
        "note": "With parameter yaml file the Process can be initiated with `Process(name=\"hello_world\", param_file=\"parameters/example.yaml\")`",
        "example": """process_hw = Process(
    name="hello_world",
    script=\"\"\"#!/bin/bash
echo 'Starting process...'
echo 'Hello World!' > output.txt
cat output.txt
\"\"\"
)
# This Process can be executed with `process_hw.execute()`
""",
    "yaml_example": """- scope: process
  name: "hello_world"
  script: |
    #!/bin/bash
    echo 'Starting process...'
    echo 'Hello World!' > output.txt
    cat output.txt
"""
    },

    "example_python_script": {
        "category": "example",
        "description": "Simple example that runs an inline Python script.",
        "note": "With a parameter YAML file, this process can be initiated using `Process(name=\"python_example\", param_file=\"parameters/example_python.yaml\")`.",
        "example": """process_python = Process(
    name="python_example",
    script=\"\"\"#!/usr/bin/env python3
print("Hello from Python")
print("2 + 2 =", 2 + 2)
\"\"\"
)
# This Process can be executed with `process_python.execute()`
""",
        "yaml_example": """- scope: process
    name: "python_example"
    script: |
        #!/usr/bin/env python3
        print("Hello from Python")
        print("2 + 2 =", 2 + 2)
"""
    },

    "example_r_script": {
        "category": "example",
        "description": "Simple example that runs an inline R script.",
        "note": "With a parameter YAML file, this process can be initiated using `Process(name=\"r_example\", param_file=\"parameters/example_r.yaml\")`.",
        "example": """process_r = Process(
    name="r_example",
    script=\"\"\"#!/usr/bin/env Rscript
cat("Hello from R\\n")
print(2 + 2)
\"\"\"
)
# This Process can be executed with `process_r.execute()`
""",
        "yaml_example": """- scope: process
    name: "r_example"
    script: |
        #!/usr/bin/env Rscript
        cat("Hello from R\\n")
        print(2 + 2)
    """
    },

    "example_script_file_with_parameters": {
        "category": "example",
        "description": "Run a Python script from file with parameter substitution.",
        "note": "With a parameter YAML file, this process can be initiated using `Process(name=\"python_file\", param_file=\"parameters/example_file.yaml\")`.",
        "example": """process_file = Process(
    name="python_file",
    script_file="scripts/hello.py",
    script_parameters={
        "APPNAME": "JAWM",
        "BYEMSG": "GOOD BYE!",
        "FRUITLIST": "['Apple', 'Banana', 'Orange']"
    }
)
# This Process can be executed with `process_file.execute()`
""",
        "yaml_example": """- scope: process
    name: "python_file"
    script_file: "scripts/hello.py"
    script_parameters:
        APPNAME: "JAWM"
        BYEMSG: "GOOD BYE!"
        FRUITLIST: "['Apple', 'Banana', 'Orange']"
    """
    },

    "example_script_file_with_parameters_file": {
        "category": "example",
        "description": "Run a Python script from file with parameters provided via an external .rc or .env-style file.",
        "note": "With a parameter YAML file, this process can be initiated using `Process(name=\"python_file_params\", param_file=\"parameters/example_params.yaml\")`.",
        "example": """process_params = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc"
)
# This Process can be executed with `process_params.execute()`
""",
        "yaml_example": """- scope: process
    name: "python_file_params"
    script_file: "scripts/hello.py"
    script_parameters_file: "scripts/hello.rc"
    """
    },

    "example_conditional_when": {
        "category": "example",
        "description": "Example showing how to conditionally skip a process using the `when` parameter.",
        "note": "The `when` parameter can be a boolean or a function returning a boolean. If False, the process will be skipped entirely.",
        "example": """process_skip = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc",
    when=False
)
# This process will be skipped because `when=False`

# Example of dynamic skipping:
# when=lambda: os.path.exists("input.txt")
""",
        "yaml_example": """- scope: process
    name: "python_file_params"
    script_file: "scripts/hello.py"
    script_parameters_file: "scripts/hello.rc"
    when: false
    """
    },

    "example_hello_world_slurm": {
        "category": "example",
        "description": "Hello World example running on Slurm.",
        "note": "With a parameter YAML file, this process can be initiated using `Process(name=\"hello_world_slurm\", param_file=\"parameters/example_slurm.yaml\")`.",
        "example": """process_hw_slurm = Process(
    name="hello_world_slurm",
    script=\"\"\"#!/bin/bash
echo 'Starting process...'
echo 'Hello World from Slurm!' > output.txt
cat output.txt
\"\"\",
    manager="slurm",
    manager_slurm={"partition":"dedicated"},
    logs_directory="logs_slurm"
)
# This Process can be executed with `process_hw_slurm.execute()`
""",
        "yaml_example": """- scope: process
    name: "hello_world_slurm"
    script: |
        #!/bin/bash
        echo 'Starting process...'
        echo 'Hello World from Slurm!' > output.txt
        cat output.txt
    manager: "slurm"
    manager_slurm:
        partition: "dedicated"
    logs_directory: "logs_slurm"
"""
    },

    "example_slurm_apptainer": {
        "category": "example",
        "description": "Run a Bash script using an Apptainer container with Slurm as the process manager.",
        "note": "This example shows how to combine container execution, environment variables, and Slurm resource options. With a parameter YAML file, this process can be initiated using `Process(name=\"slurm_apptainer\", param_file=\"parameters/slurm_apptainer.yaml\")`.",
        "example": """process_apptainer = Process(
        name="slurm_apptainer",
        script=\"\"\"#!/bin/bash
echo $HOSTNAME
echo $MY_VAR
\"\"\",
        environment='apptainer',
        container="/images/python.sif",
        env={
            "MY_VAR": "APP_Value",
            "ANOTHER_VAR": "ANOTHER_VAR"
        },
        manager="slurm",
        manager_slurm={"partition": "dedicated", "mem": "4G"},
        logs_directory="logs_slurm"
    )
    # This process runs via Slurm inside the specified Apptainer container.
    # Use process_apptainer.execute() to run.
    """,
        "yaml_example": """- scope: process
    name: "slurm_apptainer"
    script: |
        #!/bin/bash
        echo $HOSTNAME
        echo $MY_VAR
    environment: "apptainer"
    container: "/images/python.sif"
    env:
        MY_VAR: "APP_Value"
        ANOTHER_VAR: "ANOTHER_VAR"
    manager: "slurm"
    manager_slurm:
        partition: "dedicated"
        mem: "4G"
    logs_directory: "logs_slurm"
    """
    },

    "example_docker_container": {
        "category": "example",
        "description": "Run a Bash script inside a Docker container using the default local manager.",
        "note": "This example runs locally using Docker as the execution environment. With a parameter YAML file, this process can be initiated using `Process(name=\"docker_example\", param_file=\"parameters/docker_example.yaml\")`.",
        "example": """process_docker = Process(
        name="docker_example",
        script=\"\"\"#!/bin/bash
echo $HOSTNAME
echo $MY_VAR
\"\"\",
        environment='docker',
        container="ubuntu:20.04",
        env={
            "MY_VAR": "HelloFromDocker"
        }
    )
    # This process runs locally inside the specified Docker container.
    # Use process_docker.execute() to run.
    """,
        "yaml_example": """- scope: process
    name: "docker_example"
    script: |
        #!/bin/bash
        echo $HOSTNAME
        echo $MY_VAR
    environment: "docker"
    container: "ubuntu:20.04"
    env:
        MY_VAR: "HelloFromDocker"
    """
    },

    "example_with_dependencies": {
        "category": "example",
        "description": "Demonstrates how to define dependencies between processes using `depends_on`.",
        "note": "`depends_on` can be a single process name or a list of process names. The current process will only run after all listed dependencies have completed successfully. With a parameter YAML file, this process can be initiated using `Process(name=\"process_A\", param_file=\"parameters/dependency.yaml\")`.",
        "example": """process_dependency = Process(
    name="process_A",
    depends_on=["process_B", "process_C"]
)
# This process will wait for both process_B and process_C to finish before running.
""",
        "yaml_example": """- scope: process
    name: "process_A"
    depends_on:
        - "process_B"
        - "process_C"
    """
    },

    "example_fastqc": {
        "category": "example",
        "description": "Run a FastQC quality check inside an Apptainer container using Slurm.",
        "note": "This demonstrates containerized execution with Slurm, suitable for bioinformatics workflows. With a parameter YAML file, this process can be initiated using `Process(name=\"fastqc_apptainer\", param_file=\"parameters/fastqc_apptainer.yaml\")`.",
        "example": """fastqc_apptainer = Process(
    name="fastqc_apptainer",
    script=\"\"\"#!/bin/bash
mkdir output
fastqc -o output/ input/reads.fastq
\"\"\",
    container="/images/fastqc.sif",
    environment="apptainer",
    manager="slurm"
)
# This Process can be executed with `fastqc_apptainer.execute()`
""",
        "yaml_example": """- scope: process
    name: "fastqc_apptainer"
    script: |
        #!/bin/bash
        mkdir output
        fastqc -o output/ input/reads.fastq
    container: "/images/fastqc.sif"
    environment: "apptainer"
    manager: "slurm"
    """
    },

    "howto_set_monitoring": {
        "category": "howto",
        "description": "A global JAWM monitoring directory can be set with setting up `JAWM_MONITORING_DIRECTORY` environment varriable",
        "note": "This directory would store the tracking info of different jobs with Job ID, log location, current state, etc. It can comes handy, if JAWM job management requires to be visualized.",
        "example": """# With shell commands, can be kept permanantly if added to something like ~/.bashrc
export JAWM_MONITORING_DIRECTORY="/path/monitoring"
# With python per script
os.environ["JAWM_MONITORING_DIRECTORY"] = "/path/monitoring"
        """
    },

    "howto_get_process_value": {
        "category": "howto",
        "description": "Any applied Process class value can be retrieved by calling the initiated class",
        "example": """# If a Process is initiated with `process_hw = Process(...)`, parameters can be retrieved like below:
print(process_hw.name)
print(process_hw.hash)
print(process_hw.log_path)
        """
    },

    "howto_yaml_global_value": {
        "category": "howto",
        "description": "User can set global values for Processes through yaml file using global scope.",
        "note": "Global values can be overwritten by the Process name specific values or inline class values.",
        "yaml_example": """- scope: global
  retries: 3
  monitoring_directory: "monitoring"
  logs_directory: "logs_slurm"
  manager: "slurm"
  manager_slurm: {"partition":"cluster", "mem":"2GB"}
        """
    },

    "howto_yaml_process_value": {
        "category": "howto",
        "description": "User can set Process specific values for a Processes by it's name through yaml file using process scope.",
        "note": "Process name specific values will override the global scope values.",
        "yaml_example": """- scope: process
  name: "process_name"
  environment: "apptainer"
  container: "/images/python.sif"
        """
    },

    "howto_process_value_priority": {
        "category": "howto",
        "description": "The values of a Process can have different priority based on how it is injected. Higher-priority values override lower-priority ones.",
        "note": "The priority order from lowest to highest is:\n\n"
                "1. Global parameters from YAML (scope: global)\n"
                "2. Process-specific parameters from YAML (scope: process, name: <process_name>)\n"
                "3. Inline keyword arguments passed directly to the Process constructor\n\n"
                "This allows you to set general defaults globally, override them for specific processes in YAML, "
                "and override everything explicitly in Python when needed.",
        "example": """# parameters.yaml
- scope: global
  retries: 1

- scope: process
  name: "my_task"
  retries: 2

# Python code
proc = Process(
    name="my_task",
    param_file="parameters.yaml",
    retries=3
)
# Final value of `retries` will be 3
"""
    },

    "howto_set_logging_level": {
        "category": "howto",
        "description": "User can set logging level with `set_log_level` class method",
        "note": "Log level should be `INFO` to get the best outcomes. As it is the default value, no need to do anything in general.",
        "default": "INFO",
        "example": """from jawm import Process
Process.set_log_level("INFO")
        """
    },

    "howto_reset_stop_future_even": {
        "category": "howto",
        "description": "`stop_future_event` acts like a global stop signal for the entire workflow system. If any process fails it may get triggered and prevent future processes to be executed. `Process.stop_future_event.clear() would reset the stop flag to allow future processes to run again.",
        "note": "This can be useful in case of Notebook use.",
        "example": """from jawm import Process
Process.stop_future_event.clear()
        """
    },

}
