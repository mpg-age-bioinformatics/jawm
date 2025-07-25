# Process Parameters Reference

### `name`

- **Category**: `parameter`
- **Type**: `str`
- **Required**: `True`

Name of the process. Used to identify and track process executions.

_**Note**_: Unique process name is preferred for easier identification and to avoid conflicts.

**Example:**
```python
name="my_process"
```
**YAML Example:**
```yaml
name: "my_process"
```

---

### `hash`

- **Category**: `parameter`
- **Type**: `str`

A generated 7 digit hash. Used to identify and track process executions.

_**Note**_: Process hash would be generated automatically when a Process initiated. User doesn't need to provide any value.


---

### `param_file`

- **Category**: `parameter`
- **Type**: `str or list of str`

YAML file or list of YAML files or a directory containing YAMLs (on top level), consist of possible parameters.

_**Note**_: Needs to be inputted directly in the Process call or defined with class level variable `Procss.default_param_file`. This parameter defines the YAML file(s) that can shape the Process.

**Example:**
```python
param_file="parameters/param1.yaml"
# or with multiple files
param_file=["parameters/param1.yaml", "parameters/param2.yaml"]
# or with directory containing yamls
param_file="parameters"
```

---

### `default_param_file`

- **Category**: `class parameter`
- **Type**: `str or list of str`

Class level variable to set fallback `param_file` for any instance. YAML file or list of YAML files or a directory containing YAMLs (on top level), consist of possible parameters.

_**Note**_: Needs to be inputted directly in the Process call or defined with class level variable `Procss.default_param_file`. This parameter defines the YAML file(s) that can shape the Process.

**Example:**
```python
jawm.Process.default_param_file="parameters/param1.yaml"
# or with multiple files
jawm.Process.default_param_file=["parameters/param1.yaml", "parameters/param2.yaml"]
# or with directory containing yamls
jawm.Process.default_param_file="parameters/"
```

---

### `script`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `#!/bin/bash`

Inline script content to be executed. Inline script would have the higher preference.

_**Note**_: Script requires to have a shebang initiation as the first line, such as `#!/bin/bash` or `#!/usr/bin/env python3`.

**Example:**
```python
script=\"\"\"#!/usr/bin/env python3
for fruit in ["Apple", "Banana", "Ananas"]:
    print(f"Fruit: {fruit}")
\"\"\"
```

**YAML Example:**
```yaml
script: |
  #!/usr/bin/env python3
  for fruit in ["Apple", "Banana", "Ananas"]:
      print(f"Fruit: {fruit}")
```

---

### `script_file`

- **Category**: `parameter`
- **Type**: `str`

Path to an external script file to execute.

_**Note**_: Script file requires to have a shebang initiation as the first line, such as `#!/bin/bash` or `#!/usr/bin/env python3`.

**Example:**
```python
script_file="scripts/run.sh"
```

**YAML Example:**
```yaml
script_file: "scripts/run.sh"
```

---

### `script_variables`

- **Category**: `parameter`
- **Type**: `dict`

Dictionary of parameters to substitute into the script.

_**Note**_: Parameter values will substitute the placeholder(s) in the script. Please be cautious as any wrong use of parameters can break the script.

**Example:**
```python
script_variables={
    "APPNAME": "JAWM",
    "BYEMSG": "GOOD BYE!",
    "FRUITLIST": "['Apple', 'Banana', 'Orange']"
}
```

**YAML Example:**
```yaml
script_variables:
  APPNAME: "JAWM"
  BYEMSG: "GOOD BYE!"
  FRUITLIST: "['Apple', 'Banana', 'Orange']"
```

---

### `script_variables_file`

- **Category**: `parameter`
- **Type**: `str`

File containing either key=value pairs or a YAML dictionary for script placeholder substitution.

**Example:**
```python
script_variables_file="params.env"
```

**YAML Example:**
```yaml
script_variables_file: "params.env"
```

---

### `project_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `.`

Directory for logs, parameters, and outputs.

**Example:**
```python
project_directory="/data/project1"
```

**YAML Example:**
```yaml
project_directory: "/data/project1"
```

---

### `logs_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `./logs`

Directory to store logs for the process.

**Example:**
```python
logs_directory="/data/logs"
```

**YAML Example:**
```yaml
logs_directory: "/data/logs"
```

---

### `error_summary_file`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `<logs_directory>/error_summary.log`

Path to a log file summarizing all the errors with time records.

_**Note**_: This should be the go-to file while checking for error logs.

**Example:**
```python
error_summary_file="logs/error_summary.log"
```
**YAML Example:**
```yaml
error_summary_file: "logs/error_summary.log"
```

---

### `monitoring_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `~/.jawm/monitoring`

Directory used for monitoring process status. Completed or Running jobs with basic details can be found in this location.

_**Note**_: Can be set via env var `JAWM_MONITORING_DIRECTORY`.

**Example:**
```python
monitoring_directory="/jawm/monitoring"
```
**YAML Example:**
```yaml
monitoring_directory: "/jawm/monitoring"
```

---

### `depends_on`

- **Type**: `str` or `list of str`
- **Description**: Specifies the processes that must complete before this process starts. Accepts a single process name/hash or a list of them.
- **Note**: This ensures proper execution order in workflows. All dependencies must exist in the same registry scope.
- **Example**:
```python
depends_on=["step1", "step2"]
```
**YAML Example:**
```yaml
depends_on:
  - "step1"
  - "step2"
```

---

### `run_in_detached`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `False`

Whether the process should run in detached.

_**Note**_: If run_in_detached is True, the process runs in a background thread, allowing the main program to continue without blocking.

**Example:**
```python
run_in_detached=False
```
**YAML Example:**
```yaml
run_in_detached: False
```

---

### `manager`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `local`
- **Allowed Values**: ['local', 'slurm']

Specifies which execution manager to use.

**Example:**
```python
manager="slurm"
```
**YAML Example:**
```yaml
manager: "slurm"
```

---

### `env`

- **Category**: `parameter`
- **Type**: `dict`

Environment variables to set for the process.

**Example:**
```python
env={"PATH": "/usr/local/bin", "THREADS": "4"}
```
**YAML Example:**
```yaml
env:
  PATH: "/usr/local/bin"
  THREADS: "4"
```

---

### `retries`

- **Category**: `parameter`
- **Type**: `int`
- **Default**: `0`

Number of times to retry the process if it fails.

**Example:**
```python
retries=2
```
**YAML Example:**
```yaml
retries: "2"
```

---

### `retry_overrides`

- **Category**: `parameter`  
- **Type**: `dict[int -> dict]`  

Overrides specific parameters for each retry attempt. Keys represent retry attempt numbers (1-based).

_**Note**_: Supports both fixed values and relative updates (e.g., `+2`, `+20%`) for numeric fields like memory or time. Decimal values like `3.2G` are allowed, but may be rounded by Slurm depending on system configuration.

**Example:**
```python
retry_overrides = {
    1: {"manager_slurm": {"--partition": "debug", "--mem": "+100%", "--time": "+60"}},
    2: {"manager_slurm": {"--mem": "3.2G", "--time": "00:05:00"}},
    3: {"manager_slurm": {"--mem": "+1", "--time": "+50%"}}
}
```
**YAML Example:**
```yaml
retry_overrides:
  1:
    manager_slurm:
      --partition: "debug"
      --mem: "+100%"
      --time: "+60"
  2:
    manager_slurm:
      --mem: "3.2G"
      --time: "00:05:00"
  3:
    manager_slurm:
      --mem: "+1"
      --time: "+50%"
```

---

### `error_strategy`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `retry`

Strategy to follow when an error occurs.

**Example:**
```python
error_strategy="fail"
```
**YAML Example:**
```yaml
error_strategy: "fail"
```

---

### `when`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `True`

Conditional expression or boolean that determines whether to run the process.

_**Note**_: The `when` parameter can be a boolean or a function returning a boolean. If False, the process will be skipped entirely. Dynamic skipping also possible with `when=lambda: os.path.exists("input.txt")`.

**Example:**
```python
when=False
```
**YAML Example:**
```yaml
when: false
```

---

### `before_script`

- **Category**: `parameter`
- **Type**: `str`

A one-line or chained shell (bash) command to be executed before the main script starts.

**Example:**
```python
before_script="echo Preparing..."
```
**YAML Example:**
```yaml
before_script: "echo Preparing..."
```

---

### `after_script`

- **Category**: `parameter`
- **Type**: `str`

A one-line or chained shell (bash) command to be executed after the main script ends.

**Example:**
```python
after_script="echo Done."
```
**YAML Example:**
```yaml
after_script: "echo Done."
```

---

### `container_before_script`

- **Category**: `parameter`
- **Type**: `str`

A one-line or chained shell (bash) command to be executed inside container before the main script starts.

**Example:**
```python
container_before_script="source .vars.rc"
```
**YAML Example:**
```yaml
container_before_script: "source .vars.rc"
```

---

### `container_after_script`

- **Category**: `parameter`
- **Type**: `str`

A one-line or chained shell (bash) command to be executed inside container after the main script ends.

**Example:**
```python
container_after_script="echo Done."
```
**YAML Example:**
```yaml
container_after_script: "echo Done."
```

---

### `manager_slurm`

- **Category**: `parameter`
- **Type**: `dict`

Slurm manager-specific options (e.g., memory, time).

**Example:**
```python
manager_slurm={"--mem": "4G", "--time": "01:00:00"}
```
**YAML Example:**
```yaml
manager_slurm: {"--mem": "4G", "--time": "01:00:00"}
```

---

### `environment`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `local`
- **Allowed Values**: ["local", "docker", "apptainer"]

Execution environment type.

**Example:**
```python
environment="docker"
```
**YAML Example:**
```yaml
environment: "docker"
```

---

### `container`

- **Category**: `parameter`
- **Type**: `str`

Container image to use for execution.

**Example:**
```python
container="ubuntu:20.04"
```
**YAML Example:**
```yaml
container: "ubuntu:20.04"
```

---

### `environment_apptainer`

- **Category**: `parameter`
- **Type**: `dict`

Options for running the process inside Apptainer.

**Example:**
```python
environment_apptainer={"--bind": ["/data"]}
```
**YAML Example:**
```yaml
environment_apptainer: {"--bind": ["/data"]}
```

---

### `environment_docker`

- **Category**: `parameter`
- **Type**: `dict`

Options for running the process inside Docker.

**Example:**
```python
environment_docker={"--cpus": "2"}
```
**YAML Example:**
```yaml
environment_docker: {"--cpus": "2"}
```

---
