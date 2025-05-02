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
        "note": "This example shows how to combine container execution, environment variables, and Slurm resource options.",
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
        "note": "This example runs locally using Docker as the execution environment.",
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
        "note": "`depends_on` can be a single process name or a list of process names. The current process will only run after all listed dependencies have completed successfully.",
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
    }

}
