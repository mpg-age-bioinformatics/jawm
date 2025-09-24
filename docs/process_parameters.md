# Process Parameters Reference


> This reference reflects the current jawm `Process` parameters and defaults. Values are merged in this order (lowest → highest): class `default_parameters` < YAML `global` < YAML process block < `**kwargs` < explicit args < class `override_parameters`.


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
- **Type**: `str` (read-only)

A generated **10-character** identifier used to track executions: the first **6** characters come from a SHA-256 of the current parameters; the last **4** are random (lowercase letters/digits) to avoid collisions. Generated at init; not user-supplied.

---

### `param_file`

- **Category**: `parameter`
- **Type**: `str` or `list[str]`

YAML file(s) or a directory of YAMLs that define global and process-scoped parameters. Process-specific blocks override global ones.

**Example:**
```python
param_file="parameters/params.yaml"
# multiple files:
param_file=["parameters/base.yaml", "parameters/override.yaml"]
# directory containing yamls:
param_file="parameters"
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

Path to an external script file to execute. File must start with a shebang.

**Example:**
```python
script_file="scripts/run.sh"
```
**YAML Example:**
```yaml
script_file: "scripts/run.sh"
```

---

### `var`

- **Category**: `parameter`
- **Type**: `dict`

Key–value pairs to substitute into `{{PLACEHOLDER}}` occurrences in the script. Unresolved placeholders trigger warnings under validation.

**Example:**
```python
var={
  "APPNAME": "jawm",
  "THREADS": "4"
}
```

**YAML Example:**
```yaml
var:
  APPNAME: "jawm"
  THREADS: "4"
```

---

### `var_file`

- **Category**: `parameter`
- **Type**: `str`

Path to a YAML or `key=value` file providing placeholders for substitution. Merged with `var` (file values can be overridden by inline ones).

**Example:**
```python
var_file="script/vars.yaml"
```
**YAML Example:**
```yaml
var_file: "script/vars.yaml"
```

---

### `project_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `.`

Base directory for outputs and logs. Resolved to an absolute path.

**YAML Example:**
```yaml
project_directory: "/data/project1"
```

---

### `logs_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `<project_directory>/logs`

Directory where per-run logs are written (absolute path).

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

Central log that collects summarized errors across runs.

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
- **Default**: `~/.jawm/monitoring` or `JAWM_MONITORING_DIRECTORY`

Directory used for state tracking (e.g., Running/Completed).

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

- **Category**: `parameter`
- **Type**: `str` or `list[str]`

Processes (by `name` or `hash`) that must finish successfully before this process can run. Accepts a single item or a list.

_**Note**_: This ensures proper execution order in workflows. All dependencies must exist in the same registry scope.

**Example**:
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

### `allow_skipped_deps`

- **Category**: `parameter`  
- **Type**: `bool`  
- **Default**: `True`  

Whether to treat skipped dependencies as acceptable; if `False`, process only runs when all dependencies succeeded.

**Example:**
```python
allow_skipped_deps=False
```
**YAML Example:**
```yaml
allow_skipped_deps: false
```

---

### `manager`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `local`
- **Allowed**: `local`, `slurm`, `kubernetes`

Selects the execution backend. Validation fails for unsupported values.

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

Environment variables to merge into the process environment.

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

### `inputs`

- **Category**: `parameter`
- **Type**: `dict`

Optional metadata to describe inputs. Not interpreted by jawm at runtime (for readability or external tooling).

_**Note**_: Can be used in script with `{{jawm.Process.inputs}}`

---

### `outputs`

- **Category**: `parameter`
- **Type**: `dict`

Optional metadata to describe outputs. Not interpreted by jawm at runtime.

_**Note**_: Can be used in script with `{{jawm.Process.outputs}}`

---

### `retries`

- **Category**: `parameter`
- **Type**: `int`
- **Default**: `0`

How many times to retry after the initial attempt fails. Total attempts = `1 + retries`.

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
- **Allowed**: `retry`, `fail`

What to do on failure. If set to `fail`, any non-zero exit stops immediately and jawm forces `retries=0`.

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
- **Type**: `bool` or `callable`
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

### `manager_kubernetes`

- **Category**: `parameter`
- **Type**: `dict`

Kubernetes manager-specific options (e.g., namespace, restartPolicy).

_**Note**_: These options are passed directly into the generated Kubernetes Job manifest.

_**Supported keys**_:

- **`namespace`** *(str)*  
  Namespace to create the Job in. If not provided, defaults to your current
  kubectl context namespace.

- **`backoffLimit`** *(int, default: `0`)*  
  Number of retries for failed pods at the Kubernetes Job level.  
  Recommended to keep at `0` since jawm handles retries itself.

- **`ttlSecondsAfterFinished`** *(int, default: `600`)*  
  Time in seconds before Kubernetes cleans up the finished Job.

- **`restartPolicy`** *(str, default: `"Never"`)*  
  Pod restart policy. Valid values: `"Never"`, `"OnFailure"`.

- **`resources`** *(dict)*  
  Container resource requests/limits, e.g.:
  ```yaml
  resources:
    requests: { cpu: "100m", memory: "128Mi" }
    limits:   { cpu: "1", memory: "1Gi" }
  ```

- **`nodeSelector`** *(dict)*  
  Node selector labels to influence scheduling.

- **`tolerations`** *(list[dict])*  
  Pod tolerations for tainted nodes.

- **`imagePullSecrets`** *(str | list[str] | list[dict])*  
  Secrets for pulling images from private registries.  
  Can be a string, list of strings, or list of `{name: ...}` objects.

- **`serviceAccountName`** *(str)*  
  Service account name to run the pod with.

- **`volumes`** *(list[dict])*  
  Pod-level volume definitions.

- **`volumeMounts`** *(list[dict])*  
  Container-level mounts for the above volumes.

- **`activeDeadlineSeconds`** *(int)*  
  Maximum allowed run time (in seconds) before Kubernetes forcibly terminates the pod.

- **`labels`** *(dict)*  
  Extra labels merged into Job and Pod metadata.  
  jawm always adds:  
  - `jawm-name: <process_name>`  
  - `jawm-hash: <hash>`

- **`annotations`** *(dict)*  
  Extra annotations merged into Job and Pod metadata.

**Example (Python):**
```python
manager_kubernetes={
    "namespace": "jawm",
    "backoffLimit": 0,
    "ttlSecondsAfterFinished": 120,
    "nodeSelector": {"kubernetes.io/os": "linux"},
    "labels": {"team": "workflow"}
}
```

**YAML Example:**
```yaml
manager_kubernetes:
  namespace: "jawm"
  backoffLimit: 0
  ttlSecondsAfterFinished: 120
  nodeSelector:
    kubernetes.io/os: "linux"
  labels:
    team: "workflow"
```

---

### `environment`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `local`
- **Allowed**: `local`, `docker`, `apptainer`

Selects the runtime environment.

_**Note:**_ If no `container` is provided, the environment is forced to `local` at runtime.

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

Container image reference (e.g., `ubuntu:22.04` for Docker, or `/path/tool.sif` for Apptainer). Required when using a non-`local` environment.

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

Extra flags for Apptainer (passed as-is), e.g., `{"--bind": ["/data"]}`.

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

Extra flags for Docker (passed as-is), e.g., `{"--cpus": "2"}`.

**Example:**
```python
environment_docker={"--cpus": "2"}
```
**YAML Example:**
```yaml
environment_docker: {"--cpus": "2"}
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

### `validation`

- **Category**: `parameter`
- **Type**: `bool` or `str` (`"basic"`/`"strict"`)
- **Default**: `False`

Enable pre-run checks. `basic` logs errors; `strict` also treats warnings as fatal and sets `when=False` so the process is skipped.

_**Note:**_ If `validation` is True it would do the basic validation

**Example:**
```python
validation=True
```
**YAML Example:**
```yaml
validation: true
```

---

### `resume`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `False`

If `True`, skip execution when a previous run with the same parameter hash has already completed successfully.

**Example:**
```python
resume=True
```
**YAML Example:**
```yaml
resume: true
```

---

### `parallel`

- **Category**: `parameter`  
- **Type**: `bool`  
- **Default**: `True`  

If `True`, the process runs in parallel with others. If `False`, execution is serialized — the next process waits until this one finishes.

**Example:**
```python
parallel=False
```
**YAML Example:**
```yaml
resume: false
```

---

### `always_run`

- **Category**: `parameter`  
- **Type**: `bool`  
- **Default**: `False`  

Whether the process should run even if something failed. It does not override when: `when=False` still skips.

**Example:**
```python
always_run=True
```
**YAML Example:**
```yaml
always_run: true
```

---

