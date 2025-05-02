# Process Examples

### `example_hello_world`

- **Category**: `example`

Basic Hello World example with default setup.

_**Note**_: With parameter YAML file the Process can be initiated with `Process(name="hello_world", param_file="parameters/example.yaml")`

**Example:**
```python
process_hw = Process(
    name="hello_world",
    script="""#!/bin/bash
echo 'Starting process...'
echo 'Hello World!' > output.txt
cat output.txt
"""
)
# This Process can be executed with `process_hw.execute()`
```

**YAML Example:**
```yaml
- scope: process
  name: "hello_world"
  script: |
    #!/bin/bash
    echo 'Starting process...'
    echo 'Hello World!' > output.txt
    cat output.txt
```

---

### `example_python_script`

- **Category**: `example`

Simple example that runs an inline Python script.

_**Note**_: With a parameter YAML file, this process can be initiated using `Process(name="python_example", param_file="parameters/example_python.yaml")`.

**Example:**
```python
process_python = Process(
    name="python_example",
    script="""#!/usr/bin/env python3
print("Hello from Python")
print("2 + 2 =", 2 + 2)
"""
)
# This Process can be executed with `process_python.execute()`
```

**YAML Example:**
```yaml
- scope: process
  name: "python_example"
  script: |
    #!/usr/bin/env python3
    print("Hello from Python")
    print("2 + 2 =", 2 + 2)
```

---

### `example_r_script`

- **Category**: `example`

Simple example that runs an inline R script.

_**Note**_: With a parameter YAML file, this process can be initiated using `Process(name="r_example", param_file="parameters/example_r.yaml")`.

**Example:**
```python
process_r = Process(
    name="r_example",
    script="""#!/usr/bin/env Rscript
cat("Hello from R\\n")
print(2 + 2)
"""
)
# This Process can be executed with `process_r.execute()`
```

**YAML Example:**
```yaml
- scope: process
  name: "r_example"
  script: |
    #!/usr/bin/env Rscript
    cat("Hello from R\\n")
    print(2 + 2)
```

---

### `example_script_file_with_parameters`

- **Category**: `example`

Run a Python script from file with parameter substitution.

_**Note**_: With a parameter YAML file, this process can be initiated using `Process(name="python_file", param_file="parameters/example_file.yaml")`.

**Example:**
```python
process_file = Process(
    name="python_file",
    script_file="scripts/hello.py",
    script_parameters={
        "APPNAME": "JAWM",
        "BYEMSG": "GOOD BYE!",
        "FRUITLIST": "['Apple', 'Banana', 'Orange']"
    }
)
# This Process can be executed with `process_file.execute()`
```

**YAML Example:**
```yaml
- scope: process
  name: "python_file"
  script_file: "scripts/hello.py"
  script_parameters:
    APPNAME: "JAWM"
    BYEMSG: "GOOD BYE!"
    FRUITLIST: "['Apple', 'Banana', 'Orange']"
```

---

### `example_script_file_with_parameters_file`

- **Category**: `example`

Run a Python script from file with parameters provided via an external .rc or .env-style file.

_**Note**_: With a parameter YAML file, this process can be initiated using `Process(name="python_file_params", param_file="parameters/example_params.yaml")`.

**Example:**
```python
process_params = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc"
)
# This Process can be executed with `process_params.execute()`
```

**YAML Example:**
```yaml
- scope: process
  name: "python_file_params"
  script_file: "scripts/hello.py"
  script_parameters_file: "scripts/hello.rc"
```

---

### `example_conditional_when`

- **Category**: `example`

Example showing how to conditionally skip a process using the `when` parameter.

_**Note**_: The `when` parameter can be a boolean or a function returning a boolean. If False, the process will be skipped entirely.

**Example:**
```python
process_skip = Process(
    name="python_file_params",
    script_file="scripts/hello.py",
    script_parameters_file="scripts/hello.rc",
    when=False
)
# This process will be skipped because `when=False`

# Example of dynamic skipping:
# when=lambda: os.path.exists("input.txt")
```

**YAML Example:**
```yaml
- scope: process
  name: "python_file_params"
  script_file: "scripts/hello.py"
  script_parameters_file: "scripts/hello.rc"
  when: false
```

---

### `example_hello_world_slurm`

- **Category**: `example`

Hello World example running on Slurm.

_**Note**_: With a parameter YAML file, this process can be initiated using `Process(name="hello_world_slurm", param_file="parameters/example_slurm.yaml")`.

**Example:**
```python
process_hw_slurm = Process(
    name="hello_world_slurm",
    script="""#!/bin/bash
echo 'Starting process...'
echo 'Hello World from Slurm!' > output.txt
cat output.txt
""",
    manager="slurm",
    manager_slurm={"partition":"dedicated"},
    logs_directory="logs_slurm"
)
# This Process can be executed with `process_hw_slurm.execute()`
```

**YAML Example:**
```yaml
- scope: process
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
```

---

### `example_slurm_apptainer`

- **Category**: `example`

Run a Bash script using an Apptainer container with Slurm as the process manager.

_**Note**_: This example shows how to combine container execution, environment variables, and Slurm resource options.

**Example:**
```python
process_apptainer = Process(
    name="slurm_apptainer",
    script="""#!/bin/bash
echo $HOSTNAME
echo $MY_VAR
""",
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
```

**YAML Example:**
```yaml
- scope: process
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
```

---

### `example_docker_container`

- **Category**: `example`

Run a Bash script inside a Docker container using the default local manager.

_**Note**_: This example runs locally using Docker as the execution environment.

**Example:**
```python
process_docker = Process(
    name="docker_example",
    script="""#!/bin/bash
echo $HOSTNAME
echo $MY_VAR
""",
    environment='docker',
    container="ubuntu:20.04",
    env={
        "MY_VAR": "HelloFromDocker"
    }
)
# This process runs locally inside the specified Docker container.
# Use process_docker.execute() to run.
```

**YAML Example:**
```yaml
- scope: process
  name: "docker_example"
  script: |
    #!/bin/bash
    echo $HOSTNAME
    echo $MY_VAR
  environment: "docker"
  container: "ubuntu:20.04"
  env:
    MY_VAR: "HelloFromDocker"
```

---

### `example_with_dependencies`

- **Category**: `example`

Demonstrates how to define dependencies between processes using `depends_on`.

_**Note**_: `depends_on` can be a single process name or a list of process names. The current process will only run after all listed dependencies have completed successfully.

**Example:**
```python
process_dependency = Process(
    name="process_A",
    depends_on=["process_B", "process_C"]
)
# This process will wait for both process_B and process_C to finish before running.
```

**YAML Example:**
```yaml
- scope: process
  name: "process_A"
  depends_on:
    - "process_B"
    - "process_C"
```

---
