This page documents parameters associated with `jawm.Process` instance.

There are two types of parameters in jawm Processs:

- **Process instance parameters** — applied to a specific `Process` object when it is created.
- **Class-level parameters** — applied to the `jawm.Process` class itself and affect all processes in the workflow.

Instance parameters can be provided in multiple ways:

- directly in Python when creating a `Process`
- through YAML configuration files
- through CLI overrides

---

## `name`

- **Category**: `parameter`
- **Type**: `str`
- **Required**: `True`

Name of the process.

This is the user provided primary identifier of a `Process` and is used throughout jawm to identify and track process executions, as well as logging, dependency handling, run directory naming, and generated files.

_**Note**_: Unique process name is preferred for easier identification and to avoid conflicts. Each process must have a `name`. 

**Example:**
```python
name="my_process"
```

While creating a `jawm.Process`, `name` needs to be defined in the Python code. In YAML, `name` is required to define other parameters in `- scope: process`.

**YAML Example:**
```yaml
name: "my_process"
```

---

## `hash`

- **Category**: `parameter`
- **Type**: `str` *(read-only)*

A generated 10-character identifier used to track executions: the first 6 characters come from a SHA-256 of the current parameters; the last 4 are random (lowercase letters/digits) to avoid collisions. Generated at Process initialization; not user-supplied.

_**Note**_: `hash` is an internal/reserved key and should not be set manually.

**Example log usage:**
```text
hello_world|cb6bc9hopa
```

`hash` of each instance can be used in multiple important places such as `depends_on`, `Process.wait()`

**Example `depends_on` usage:**
```python
p1 = jamw.Process(name="p1", ...)
p2 = jawm.Process(name="p2", depends_on=[p1.hash], ...)
# or use as the parameter of `execute` method to have the same depends_on outcome
# p2.execute([p1.hash])
```

**Example `jawm.Process.wait()` usage:**
```python
p1 = jamw.Process(name="p1", ...)
p2 = jawm.Process(name="p2", ...)
p1.execute()
jawm.Process.wait([p1.hash])        # to wait until p1 execution is finished
p2.execute()
```

---

## `param_file`

- **Category**: `parameter`
- **Type**: `str` or `list[str]`

Path to a YAML parameter file, multiple YAML parameter files, or a directory containing YAML files.

`param_file` is used to load process configuration from YAML. These files can define both global parameters and process-specific parameters using `scope: global` and `scope: process`.

When multiple files are provided, they are loaded and merged in order. A directory can also be provided, in which case jawm loads YAML files from that directory.

_**Note**_: `param_file` can be set in Python, but it is especially important when passed through the CLI using `-p`, because that changes precedence behavior and gives YAML higher priority than normal Python instance arguments.

**Example:**
```python
param_file="parameters/params.yaml"
```

**Multiple files Example:**
```python
param_file=["parameters/base.yaml", "parameters/override.yaml"]
```

**Directory Example:**
```python
param_file="parameters"
```

**CLI Example:**
```bash
jawm module.py -p parameters/params.yaml
```

**CLI Example with multiple files:**
```bash
jawm module.py -p parameters/base.yaml parameters/override.yaml
```

---

## `script`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `#!/bin/bash`

Inline script content to be executed by the `Process`.

If `script` is provided, jawm uses it as the main script content for the process. The script requires start with a valid shebang line such as `#!/bin/bash` or `#!/usr/bin/env python3`.

_**Note**_: The **script requires to start with a valid shebang line** such as `#!/bin/bash` or `#!/usr/bin/env python3`.

**Example:**
```python
script="""#!/usr/bin/env python3
for fruit in ["Apple", "Banana", "Ananas"]:
    print(f"Fruit: {fruit}")
"""
```

**YAML Example:**
```yaml
script: |
  #!/usr/bin/env python3
  for fruit in ["Apple", "Banana", "Ananas"]:
      print(f"Fruit: {fruit}")
```

**Common shebang examples:**

```bash
#!/bin/bash
```

```bash
#!/usr/bin/env bash
```

```python
#!/usr/bin/env python3
```

```r
#!/usr/bin/env Rscript
```

```bash
#!/usr/bin/env sh
```

The shebang defines which interpreter should execute the script. Using `/usr/bin/env` is generally preferred because it resolves the interpreter from the system `PATH`, making scripts more portable across environments.

---

## `script_file`

- **Category**: `parameter`
- **Type**: `str`

Path to an external script file to be executed by the `Process`.

Instead of embedding the script inline with `script`, you can provide a path to a script file using `script_file`. jawm reads the file content, applies placeholder substitution, and writes the processed version to the generated `<name>.script` file inside the process log directory before execution.

The referenced script file must exist and must start with a valid shebang line such as `#!/bin/bash`, `#!/usr/bin/env python3`, or `#!/usr/bin/env Rscript`.

_**Note**_: If both `script` and `script_file` are provided, the inline `script` takes precedence.

**Example:**
```python
script_file="scripts/my_script.sh"
```

**YAML Example:**
```yaml
script_file: "scripts/my_script.sh"
```

---

## `var`

- **Category**: `parameter`
- **Type**: `dict`

Dictionary of variables used for placeholder substitution inside the executable `script` or `script_file`.

Values from `var` can be referenced in scripts using the `{{KEY}}` syntax. During script generation, jawm replaces matching placeholders with the corresponding values from `var`.

**Example:**
```python
var={
    "fruit": "Apple",
    "count": 3
}
```

**YAML Example:**
```yaml
var:
  fruit: "Apple"
  count: 3
```

Variables can then be used in the script like:

**Example of var usage:**
```python
script="""#!/usr/bin/env python3
print("Fruit: {{fruit}}")
print("Count:", {{count}})
"""
```

This would generate a script equivalent to:

```python
#!/usr/bin/env python3
print("Fruit: Apple")
print("Count:", 3)
```

_**Note**_: If a placeholder such as `{{fruit}}` is not found in `var`, jawm keeps it unchanged in the generated script. This can lead to script failures if the placeholder is required by the interpreter or shell.

**Merge and override behavior**

`var` is a dict-like parameter, so it is **merged** across configuration layers instead of being replaced as a whole. If the same key appears multiple times, the value from the higher-precedence source overrides the lower-precedence one, while other keys are preserved.

For example:

```python
# lower-precedence values
var={"fruit": "Apple", "color": "red"}

# higher-precedence override
var={"fruit": "Banana"}
```

The effective merged value becomes:

```python
{"fruit": "Banana", "color": "red"}
```

**Special `mk.*` and `map.*` keys**

Keys starting with `mk.` or `map.` are treated specially. jawm also adds a short alias without the prefix.

**mk.\*** variables are treated as paths that jawm can automatically create and possibly mount.

**map.\*** variables are treated as paths that jawm can automatically mount into containerized execution environments.

Example:

```python
var={
    "mk.output": "results/output",
    "map.reference": "ref/genome.fa"
}
```

This also makes the following aliases available:

- `output`
- `reference`

So both forms can be used in scripts if needed:

```bash
{{output}}
{{mk.output}}
{{reference}}
{{map.reference}}
```

**CLI Example:**

Variables can also be injected or overridden from the CLI using `--global.var.<key>=<value>` or `--process.<process_name>.var.<key>=<value>`.

```bash
jawm module.py --global.var.fruit="Apple"
```

```bash
jawm module.py --process.my_process.var.fruit="Apple"
```

---

## `var_file`

- **Category**: `parameter`
- **Type**: `str` or `list[str]`

Path to a file, multiple files, or a directory containing variable definitions that will be loaded into the process variable dictionary.

`var_file` allows variables to be defined outside the workflow code and reused across processes. The loaded variables are merged into `var` and can be referenced in `script` or `script_file` using the `{{KEY}}` placeholder syntax.

Supported formats typically include:

- YAML files
- `.rc` style key–value files
- directories containing multiple variable files

If multiple files are provided, they are loaded in order and merged.

_**Note**_: If both `var_file` and `var` are provided, variables loaded from `var_file` are applied first and values defined in `var` override any matching keys.

**Example:**
```python
var_file="variables.yaml"
```

**Multiple files Example:**
```python
var_file=["variables/base.yaml", "variables/override.yaml"]
```

**Directory Example:**
```python
var_file="variables/"
```

**YAML Example:**
```yaml
var_file: "variables.yaml"
```

Example `variables.yaml`:

```yaml
fruit: Apple
count: 3
```

These variables can then be used inside scripts:

```python
script="""#!/usr/bin/env python3
print("Fruit: {{fruit}}")
print("Count:", {{count}})
"""
```

---

## `project_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: current working directory (`"."`)

Base working directory for the `Process`.

`project_directory` is used as the main base path for process-related files and directories. If not explicitly set, jawm uses the current working directory. By default, `logs_directory` is created under `project_directory` as `<project_directory>/logs`.

jawm resolves `project_directory` to an absolute path and creates it automatically during process execution if it does not already exist.

_**Note**_: This parameter is especially useful for keeping workflow outputs, logs, and related files organized under a single project location.

**Example:**
```python
project_directory="/data/my_project"
```

**YAML Example:**
```yaml
project_directory: "/data/my_project"
```

---

## `logs_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `<project_directory>/logs`

Directory where jawm stores logs and execution artifacts for all processes.

If not explicitly defined, jawm automatically sets `logs_directory` to a `logs` folder inside the `project_directory` (current directory by default). Each process execution then creates its own subdirectory inside this location.

Process log/run directories follow the pattern:

```text
<logs_directory>/<process.name>_<YYYYMMDD>_<HHMMSS>_<process.hash>
```

Inside each process run directory, jawm stores files such as (in additon to backed specific artifact files):

```text
<name>.script
<name>.command
<name>.output
<name>.error
<name>.id
<name>.exitcode
```

A workflow-level `error.log` file is also written inside `logs_directory` to summarize process failures.

**Example:**
```python
logs_directory="/data/my_project/logs"
```

**YAML Example:**
```yaml
logs_directory: "/data/my_project/logs"
```

**CLI Example:**

The `logs_directory` can also be set from the CLI using the `-l` option.

```bash
jawm module.py -l /data/my_project/logs
```

---

## `error_summary_file`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `<logs_directory>/error.log`

Path to the central error summary file.

When a `Process` fails, jawm appends a short summary to this file so that errors can be found quickly without checking each individual process logs/run directory. This makes `error_summary_file` the main file to inspect for a quick overview of workflow failures.

Each entry typically includes:

- timestamp
- process name
- process hash
- log folder path
- error type and message

_**Note**_: If not explicitly set, jawm uses `error.log` inside `logs_directory` (dafault to `logs`). If there's no error, there wouldn't be an error summary file.

**Example:**
```python
error_summary_file="logs/error.log"
```

**YAML Example:**
```yaml
error_summary_file: "logs/error.log"
```

---

## `monitoring_directory`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `~/.jawm/monitoring` or environment variable `JAWM_MONITORING_DIRECTORY`

Directory used by jawm to track process execution state outside the main `logs_directory`.

When enabled, jawm creates `Running/` and `Completed/` subdirectories inside `monitoring_directory` and writes lightweight state files there while a process is running and after it finishes. This is useful for quick external monitoring of active and completed jobs across managed executions. In general cases, user does not need to interact directly with this directory, and shouldnot change frequently.

Typical structure:

```text
<monitoring_directory>/
├── Running/
└── Completed/
```

Typical files:

```text
Running/local.<job_id>.txt
Completed/local.<job_id>.<exit_code>.txt
```

These files contain summary information such as process name, process hash, manager, script path, run start time, and exit code.

_**Note**_: If not explicitly set, jawm uses `JAWM_MONITORING_DIRECTORY` when available, otherwise defaults to `~/.jawm/monitoring`.

**Example:**
```python
monitoring_directory="/jawm/monitoring"
```

**YAML Example:**
```yaml
monitoring_directory: "/jawm/monitoring"
```

---

## `depends_on`

- **Category**: `parameter`
- **Type**: `str` or `list[str]`

Name or hash of one or more upstream processes that must finish before this process starts.

`depends_on` is used to define execution order in a workflow. Before running the current process, jawm waits for all listed dependencies to finish. Dependencies can be provided using either the process `name` or the generated process `hash` (recommended for better uniqeness).

_**Note**_: By default, jawm waits for dependencies to finish. If `allow_skipped_deps=False`, jawm also requires those dependencies to have completed successfully; otherwise the current process is skipped.

**Single dependency by name:**
```python
depends_on="dependant_proc_name"
```

**Single dependency by hash:**
```python
depends_on="cb6bc9hopa"
```

**Better with not hardcoded instance hash**
```python
depends_on=process_instance.hash
```

**Multiple dependencies:**
```python
depends_on=[proc_instance_1.hash, proc_instance_1.hash]
```

**YAML Example:**
```yaml
depends_on:
  - "prepare_data"
  - "run_qc"
```

**Example with process objects using `hash`:**
```python
import jawm

p1 = jawm.Process(
    name="prepare_data",
    script="""#!/bin/bash
echo "Preparing data"
"""
)

p2 = jawm.Process(
    name="run_qc",
    script="""#!/bin/bash
echo "Running QC"
""",
    depends_on=[p1.hash]
)
```

**Example with `execute(depends_on=...)`:**
```python
import jawm

p1 = jawm.Process(
    name="prepare_data",
    script="""#!/bin/bash
echo "Preparing data"
"""
)

p2 = jawm.Process(
    name="run_qc",
    script="""#!/bin/bash
echo "Running QC"
"""
)

p1.execute()
p2.execute(depends_on=[p1.hash])
```

In the `execute(depends_on=...)` form, the provided dependency list overrides the current `depends_on` value for that execution.

_**Note**_: If a dependency is not found in the registry, jawm logs a warning and skips waiting for it. If a process lists itself in `depends_on` using its own name or hash, that self-dependency is ignored.

---

## `allow_skipped_deps`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `True`

Whether to treat skipped dependencies as acceptable; if False, process only runs when all dependencies succeeded.

If `allow_skipped_deps=True`, jawm allows the current process to continue when a dependency was skipped.

_**Note**_: This parameter is mainly relevant when using `depends_on`.

**Example:**
```python
allow_skipped_deps=False
```

**YAML Example:**
```yaml
allow_skipped_deps: false
```

---

## `manager`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `local`
- **Allowed**: `local`, `slurm`, `kubernetes`

Execution backend used to launch the `Process`.

The `manager` parameter controls **where and how** the process is executed:

- **`local`** — runs the process on the local machine
- **`slurm`** — submits the process as a Slurm job
- **`kubernetes`** — creates and runs the process as a Kubernetes job

jawm validates the selected manager and dispatches execution to the corresponding backend implementation. Manager-specific options can then be provided through parameters such as `manager_slurm` or `manager_kubernetes`. 

_**Note**_: `manager` controls the execution backend, while container-related parameters such as `environment` and `container` control the runtime environment inside that backend. For example, a process may use `manager="local"` together with a containerized environment, or `manager="slurm"` to submit through a scheduler.

**Example:**
```python
manager="slurm"
```

**YAML Example:**
```yaml
manager: "slurm"
```

**CLI Example:**

**Global manager for all processes:**
```bash
jawm module.py --global.manager=kubernetes
```

**Process-specific manager:**
```bash
jawm module.py --process.p1.manager=slurm
```

---

## `manager_slurm`

- **Category**: `parameter`
- **Type**: `dict`

Slurm-specific options used when `manager="slurm"`.

`manager_slurm` is a dictionary of arguments passed to `sbatch`. Keys should be written as valid Slurm CLI options such as `--partition`, `--time`, `--mem`, `--cpus-per-task`, or `--account`.

jawm uses these values in two places:

- to generate the `#SBATCH` lines in the generated `<name>.slurm` script
- to build the final `sbatch` submission command

_**Note**_: Keys should include the option prefix such as `--time` or `-p`. Values are passed as provided.

If not explicitly defined by the user:

- `--parsable` is added automatically to make JobID parsing reliable
- `--output` and `--error` are added automatically so Slurm stdout/stderr are written to the process log files

**Example:**
```python
manager_slurm={
    "--partition": "short",
    "--time": "01:00:00",
    "--mem": "8G",
    "--cpus-per-task": 4
}
```

**YAML Example:**
```yaml
manager_slurm:
  --partition: "short"
  --time: "01:00:00"
  --mem: "8G"
  --cpus-per-task: 4
```

**Example with account and qos:**
```python
manager_slurm={
    "--account": "my_lab",
    "--qos": "normal",
    "--partition": "compute"
}
```

**Example with short and long options mixed:**
```python
manager_slurm={
    "-p": "short",
    "--time": "00:30:00",
    "-c": 2
}
```

_**Note**_: If custom `--output` or `--error` are provided in `manager_slurm` (not necessary or recommended), those values are used instead of jawm's default process log paths.

**Full Python Example:**
```python
import jawm

p = jawm.Process(
    name="align",
    manager="slurm",
    script="""#!/bin/bash
echo "Running alignment"
""",
    manager_slurm={
        "--partition": "short",
        "--time": "02:00:00",
        "--mem": "16G",
        "--cpus-per-task": 8
    }
)
```

**YAML param file example**

```yaml
- scope: global
  manager: "slurm"
  manager_slurm:
    --partition: "short"
    --time: "01:00:00"
    --mem: "8G"

- scope: process
  name: "heavy_job"
  manager_slurm:
    --partition: "long"
    --time: "12:00:00"
    --mem: "64G"
```

---

## `manager_kubernetes`

- **Category**: `parameter`
- **Type**: `dict`

Kubernetes-specific options used when `manager="kubernetes"`.

`manager_kubernetes` is used to customize the generated Kubernetes Job manifest for the process. These values are applied directly to the Job or Pod specification generated by jawm.

If a container image is not explicitly provided through `container`, jawm tries to infer a default image from the script shebang. For example, Python scripts are mapped to a Python image, R scripts to an R image, and shell scripts to a default Ubuntu image.

_**Note**_: jawm uses safe defaults for Kubernetes execution. In particular, `backoffLimit` defaults to `0` so Kubernetes does not retry failed pods independently of jawm retry handling.

**Commonly used supported keys:**

- **`namespace`** (`str`)  
  Kubernetes namespace where the Job will be created.

- **`backoffLimit`** (`int`, default: `0`)  
  Number of retries at the Kubernetes Job level.

- **`ttlSecondsAfterFinished`** (`int`, default: `600`)  
  Time in seconds before Kubernetes cleans up the finished Job.

- **`restartPolicy`** (`str`, default: `"Never"`)  
  Pod restart policy.

- **`resources`** (`dict`)  
  Container resource requests and limits.

- **`nodeSelector`** (`dict`)  
  Node selector labels for scheduling.

- **`tolerations`** (`list[dict]`)  
  Pod tolerations.

- **`imagePullSecrets`** (`str` or `list`)  
  Secret name or list of secret names for pulling container images.

- **`serviceAccountName`** (`str`)  
  Service account used to run the pod.

- **`volumes`** (`list[dict]`)  
  Additional pod-level volumes.

- **`volumeMounts`** (`list[dict]`)  
  Additional container volume mounts.

- **`activeDeadlineSeconds`** (`int`)  
  Maximum allowed runtime of the pod.

- **`labels`** (`dict`)  
  Extra labels added to the Job and Pod metadata.

- **`annotations`** (`dict`)  
  Extra annotations added to the Job and Pod metadata.

- **`workspace`** (`str` or `dict`)  
  Defines the main working directory mount for the pod. If not provided, jawm uses an ephemeral `emptyDir` mounted at `/work`.

- **`mounts`** (`list[dict]`)  
  Additional mounts exposed into the pod. Supports PVC-based mounts and `s3sync`-based mounts.

_**Note**_: jawm automatically adds labels such as `jawm-name` and `jawm-hash` to Kubernetes Job and Pod metadata.

**Example:**
```python
manager_kubernetes={
    "namespace": "jawm",
    "backoffLimit": 0,
    "ttlSecondsAfterFinished": 120,
    "resources": {
        "requests": {"cpu": "500m", "memory": "512Mi"},
        "limits": {"cpu": "2", "memory": "2Gi"}
    },
    "nodeSelector": {
        "kubernetes.io/os": "linux"
    },
    "labels": {
        "team": "workflow"
    }
}
```

**YAML Example:**
```yaml
manager_kubernetes:
  namespace: "jawm"
  backoffLimit: 0
  ttlSecondsAfterFinished: 120
  resources:
    requests:
      cpu: "500m"
      memory: "512Mi"
    limits:
      cpu: "2"
      memory: "2Gi"
  nodeSelector:
    kubernetes.io/os: "linux"
  labels:
    team: "workflow"
```

**Combined example**

A common setup is to use one PVC as the main workspace and one additional read-only reference mount:

```python
manager_kubernetes={
    "namespace": "jawm",
    "workspace": {
        "claimName": "jawm-work",
        "mountPath": "/work",
        "subPath": "runs/sample_01",
        "mkdir": True
    },
    "mounts": [
        {
            "name": "reference",
            "mode": "pvc",
            "claimName": "ref-data",
            "mountPath": "/ref",
            "readOnly": True
        }
    ]
}
```

**YAML Example:**
```yaml
manager_kubernetes:
  namespace: "jawm"
  workspace:
    claimName: "jawm-work"
    mountPath: "/work"
    subPath: "runs/sample_01"
    mkdir: true
  mounts:
    - name: "reference"
      mode: "pvc"
      claimName: "ref-data"
      mountPath: "/ref"
      readOnly: true
```


**`workspace` and `mounts`**

Two especially important `manager_kubernetes` options are `workspace` and `mounts`.

**`workspace`**

`workspace` defines the **primary working directory** for the Kubernetes job.

jawm exports this location inside the container as:

```text
JAWM_WORKSPACE=<mountPath>
```

and also builds the in-container run log directory under that workspace.

Accepted forms:

- a **string** → treated as a PVC claim name
- a **dict** → full workspace configuration

**String form:**
```python
manager_kubernetes={
    "workspace": "jawm-work"
}
```

This is treated internally like:

```python
manager_kubernetes={
    "workspace": {
        "claimName": "jawm-work"
    }
}
```

**Dict form:**
```python
manager_kubernetes={
    "workspace": {
        "claimName": "jawm-work",
        "mountPath": "/work",
        "readOnly": False,
        "mkdir": True
    }
}
```

**YAML Example:**
```yaml
manager_kubernetes:
  workspace:
    claimName: "jawm-work"
    mountPath: "/work"
    readOnly: false
    mkdir: true
```

Supported `workspace` keys:

- **`claimName`** (`str`)  
  PVC claim name to use as the workspace.

- **`mountPath`** (`str`, default: `"/work"`)  
  Absolute path inside the container.

- **`subPath`** (`str`, optional)  
  Mount only a subdirectory of the PVC.

- **`readOnly`** (`bool`, default: `False`)  
  Mount workspace as read-only.

- **`mkdir`** (`bool`, default: `False`)  
  If `True`, jawm creates the target workspace directory using an initContainer.  
  This is useful especially when `subPath` is used.

- **`storeLogs`** (`bool`, reserved/optional)  
  Reserved for workspace-based log handling.

_**Note**_: If `workspace` is not provided, or no valid `claimName` is available, jawm uses an ephemeral `emptyDir` mounted at `/work`.

---
**`mounts`**

`mounts` defines **additional mounts** exposed into the pod, beyond the main workspace.

It must be a list of mount definitions.

Each mount should define at least:

- `name`
- `mountPath`

and may define a `mode`.

Supported mount modes:

- **`pvc`** *(default)*  
  Mount an existing PVC into the container

- **`s3sync`** *(best-effort)*  
  Sync data from an S3 location into an `emptyDir` using an initContainer, with optional sync-back after successful execution

---

**`mounts` with `mode: pvc`**

Use this for additional PVC-backed mounts.

**Example:**
```python
manager_kubernetes={
    "mounts": [
        {
            "name": "reference",
            "mode": "pvc",
            "claimName": "ref-data",
            "mountPath": "/ref",
            "subPath": "genomes/hg38",
            "readOnly": True,
            "mkdir": False
        }
    ]
}
```

**YAML Example:**
```yaml
manager_kubernetes:
  mounts:
    - name: "reference"
      mode: "pvc"
      claimName: "ref-data"
      mountPath: "/ref"
      subPath: "genomes/hg38"
      readOnly: true
      mkdir: false
```

Supported keys for `mode: pvc`:

- **`name`** (`str`)  
  Logical name of the mount.

- **`claimName`** (`str`)  
  PVC claim name.

- **`mountPath`** (`str`)  
  Absolute path inside the container.

- **`subPath`** (`str`, optional)  
  Mount only a subdirectory of the PVC.

- **`readOnly`** (`bool`, default: `False`)  
  Mount as read-only.

- **`mkdir`** (`bool`, default: `False`)  
  If `True`, jawm uses an initContainer to create the target `subPath` directory when needed.

_**Note**_: `mountPath` must be an absolute path such as `/ref`. Relative paths are skipped.

---

**`mounts` with `mode: s3sync`**

Use this when you want to treat S3 data like a folder copied into the container at startup.

This is **not a live mount**. jawm creates an `emptyDir`, downloads the S3 content into it using an initContainer, and optionally uploads results back to S3 after the main process finishes successfully. This is a best-effort approch and not recommened, if not necessary. 

**Example:**
```python
manager_kubernetes={
    "mounts": [
        {
            "name": "s3data",
            "mode": "s3sync",
            "uri": "s3://my-bucket/input/",
            "mountPath": "/s3",
            "uploadUri": "s3://my-bucket/output/",
            "envFromSecret": "aws-creds",
            "region": "eu-central-1",
            "args": ["--no-progress"],
            "uploadArgs": ["--no-progress"]
        }
    ]
}
```

**YAML Example:**
```yaml
manager_kubernetes:
  mounts:
    - name: "s3data"
      mode: "s3sync"
      uri: "s3://my-bucket/input/"
      mountPath: "/s3"
      uploadUri: "s3://my-bucket/output/"
      envFromSecret: "aws-creds"
      region: "eu-central-1"
      args:
        - "--no-progress"
      uploadArgs:
        - "--no-progress"
```

Supported keys for `mode: s3sync`:

- **`name`** (`str`)  
  Logical mount name.

- **`uri`** (`str`)  
  Source S3 URI to sync from. Must start with `s3://`.

- **`mountPath`** (`str`)  
  Absolute destination path inside the container.

- **`uploadUri`** (`str`, optional)  
  S3 URI to sync back to after successful execution.

- **`envFromSecret`** (`str`, optional)  
  Kubernetes Secret containing AWS-style environment variables.

- **`region`** (`str`, optional)  
  AWS region.

- **`endpoint`** (`str`, optional)  
  Custom S3-compatible endpoint.

- **`args`** (`list[str]`, optional)  
  Extra arguments for the initial download sync.

- **`uploadArgs`** (`list[str]`, optional)  
  Extra arguments for the upload sync.

- **`image`** (`str`, optional)  
  Custom image for the S3 initContainer. Defaults to an AWS CLI image.

_**Note**_: For `uploadUri`, the upload step runs in the **main container**, so the main container image must have the required AWS CLI tooling available or the upload will fail.

---

## `environment`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `local`
- **Allowed**: `local`, `docker`, `apptainer`

Runtime environment used to execute the `Process`.

The `environment` parameter controls whether the process runs:

- directly on the host using **`local`**
- inside a **Docker** container using **`docker`**
- inside an **Apptainer** container using **`apptainer`** (or **`singularity`** as an accepted alias)

This parameter is separate from `manager`.

- `manager` controls **where the job is launched** such as `local`, `slurm`, or `kubernetes`
- `environment` controls **how the script is executed** within that manager, especially for local and Slurm execution

For containerized execution, a valid `container` must also be provided.

_**Note**_: If `environment` is set to `docker`, `apptainer`, or `singularity` but no `container` is provided, jawm falls back to `local`.

**Example:**
```python
environment="docker"
```

**YAML Example:**
```yaml
environment: "docker"
```

**Typical Python Example:**
```python
import jawm

p = jawm.Process(
    name="python_in_docker",
    script="""#!/usr/bin/env python3
print("Hello from container")
""",
    environment="docker",
    container="python:3.12"
)
```

**Typical YAML Example:**
```yaml
environment: "apptainer"
container: "/data/containers/tools.sif"
```

**Or with hosted image:**
```yaml
environment: "apptainer"
container: "docker://ubuntu:22.04"
```
`ubuntu:22.04` would result the same as the default prefix is `docker://`

**CLI Example:**
```bash
jawm module.py --global.environment="docker"
```

**Process-specific CLI Example:**
```bash
jawm module.py --process.my_process.environment="apptainer"
```

_**Related parameters**_:

- `container` — container image or `.sif` path
- `environment_docker` — extra Docker runtime options
- `environment_apptainer` — extra Apptainer runtime options
- `container_before_script` — command to run inside the container before the main script
- `container_after_script` — command to run inside the container after the main script
- `docker_run_as_user` — run Docker container with the current user UID/GID

---

## `container`

- **Category**: `parameter`
- **Type**: `str`

Container image or container file used for containerized execution.

The meaning of `container` depends on the selected runtime:

- with `environment="docker"` → Docker image, for example `python:3.12`
- with `environment="apptainer"` or `environment="singularity"` → Apptainer/Singularity image or `.sif` file
- with `manager="kubernetes"` → container image used in the Kubernetes Job

**Common examples:**

- Docker image:
```python
container="python:3.12"
```

- Apptainer image file:
```python
container="/containers/tools.sif"
```

- Apptainer image from Docker registry:
```python
container="python:3.12"     # or "docker://python:3.12"
```

**YAML Example:**
```yaml
container: "python:3.12"
```

_**Note**_: For local or Slurm execution with `environment="docker"` or `environment="apptainer"`, `container` should be set. If `environment` is non-local but `container` is missing, jawm falls back to `local` execution.

**Example with Docker:**
```python
import jawm

p = jawm.Process(
    name="run_python",
    script="""#!/usr/bin/env python3
print("Hello from Docker")
""",
    environment="docker",
    container="python:3.12"
)
```

**Example with Slurm + Apptainer:**
```python
import jawm

p = jawm.Process(
    name="cluster_job",
    manager="slurm",
    environment="apptainer",
    container="/containers/tools.sif",
    script="""#!/bin/bash
python3 /work/run.py
"""
)
```

**Example with Kubernetes:**
```python
import jawm

p = jawm.Process(
    name="k8s_python",
    manager="kubernetes",
    script="""#!/usr/bin/env python3
print("Hello from Kubernetes")
""",
    container="python:3.12"
)
```

_**Note**_: For Kubernetes, if `container` is not provided, jawm tries to infer an image from the script shebang. For example, Python scripts map to a Python image, R scripts to an R image, and shell scripts to a default Ubuntu image.

**CLI Example:**
```bash
jawm module.py --global.container="python:3.12"
```

**Process-specific CLI Example:**
```bash
jawm module.py --process.my_process.container="python:3.12"
```

---

## `environment_docker`

- **Category**: `parameter`
- **Type**: `dict`

Docker-specific runtime options used when `environment="docker"`.

`environment_docker` is passed directly to the generated `docker run` command. It is used to add Docker runtime flags such as volume mounts, port mappings, container names, network settings, or other supported Docker options.

How values are handled:

- **string / number values** are passed as `OPTION VALUE`
- **list values** are passed multiple times
- **boolean `True` values** are treated as flags and added without a value
- **boolean `False` values** are ignored

_**Note**_: `environment_docker` only affects Docker execution. To use it, `environment` must be set to `docker` and a valid `container` must also be provided.

_**Note**_: When `automated_mount=True` (default), jawm also automatically mounts the process log directory and detected `mk.*` / `map.*` paths, unless those mounts are already provided manually.

_**Note**_: If no `-w` or `--workdir` is provided and `automated_mount=True`, jawm automatically sets the container working directory to `project_directory`.

**Example:**
```python
environment_docker={
    "--volume": ["/data:/data", "/ref:/ref"],
    "--network": "host"
}
```

**YAML Example:**
```yaml
environment_docker:
  --volume:
    - "/data:/data"
    - "/ref:/ref"
  --network: "host"
```

**Example with a single volume mount:**
```python
environment_docker={
    "--volume": "/project:/project"
}
```

**Example with boolean flags:**
```python
environment_docker={
    "--ipc": "host",
    "--rm": True
}
```

**Example with short options:**
```python
environment_docker={
    "-v": ["/data:/data", "/work:/work"],
    "-p": ["8080:8080", "8888:8888"]
}
```

**Typical Python Example:**
```python
import jawm

p = jawm.Process(
    name="run_in_docker",
    script="""#!/usr/bin/env python3
print("Hello from Docker")
""",
    environment="docker",
    container="python:3.12",
    environment_docker={
        "--volume": ["/data:/data", "/work:/work"],
        "--network": "host"
    }
)
```

**Typical YAML Example:**
```yaml
environment: "docker"
container: "python:3.12"
environment_docker:
  --volume:
    - "/data:/data"
    - "/work:/work"
  --network: "host"
```

---

## `environment_apptainer`

- **Category**: `parameter`
- **Type**: `dict`

Apptainer-specific runtime options used when `environment="apptainer"` or `environment="singularity"`.

`environment_apptainer` is passed directly to the generated `apptainer exec` command. It is mainly used to add Apptainer flags such as bind mounts, writable settings, home directory control, overlays, or other supported runtime options.

How values are handled:

- **string / number values** are passed as `OPTION VALUE`
- **list values** are passed multiple times
- **boolean `True` values** are treated as flags and added without a value
- **boolean `False` values** are ignored

_**Note**_: `environment_apptainer` only affects the Apptainer command. To use Apptainer execution, `environment` must be set to `apptainer` (or `singularity`) and a valid `container` must also be provided.

_**Note**_: When `automated_mount=True` (default), jawm also automatically binds the process log directory and detected `mk.*` / `map.*` paths, unless those mounts are already provided manually.

**Example:**
```python
environment_apptainer={
    "--bind": ["/data:/data", "/ref:/ref"],
    "--cleanenv": True
}
```

**YAML Example:**
```yaml
environment_apptainer:
  --bind:
    - "/data:/data"
    - "/ref:/ref"
  --cleanenv: true
```

**Example with a single bind mount:**
```python
environment_apptainer={
    "--bind": "/project:/project"
}
```

**Example with multiple flags:**
```python
environment_apptainer={
    "--bind": ["/data:/data", "/scratch:/scratch"],
    "--cleanenv": True,
    "--containall": True,
    "--writable-tmpfs": True
}
```

**Example with Singularity-compatible short option:**
```python
environment_apptainer={
    "-B": ["/data:/data", "/ref:/ref"]
}
```

**Typical Python Example:**
```python
import jawm

p = jawm.Process(
    name="run_in_apptainer",
    script="""#!/bin/bash
python3 /work/run.py
""",
    environment="apptainer",
    container="/containers/tools.sif",
    environment_apptainer={
        "--bind": ["/data:/data", "/work:/work"],
        "--cleanenv": True
    }
)
```

**Typical YAML Example:**
```yaml
environment: "apptainer"
container: "/containers/tools.sif"
environment_apptainer:
  --bind:
    - "/data:/data"
    - "/work:/work"
  --cleanenv: true
```

---

## `docker_run_as_user`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `False`

Whether to run the Docker container as the current host user.

If `docker_run_as_user=True`, jawm adds the current host `UID:GID` to the generated `docker run` command using `-u`, unless `-u` or `--user` is already explicitly set in `environment_docker`.

This is useful to avoid permission issues on mounted files and directories.

**Example:**
```python
docker_run_as_user=True
```

**YAML Example:**
```yaml
docker_run_as_user: true
```

_**Note**_: This parameter is only relevant when `environment="docker"`.

---

## `automated_mount`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `True`

This is a special parameter that decides Whether jawm should automatically mount commonly needed paths into containerized execution environments.

When `automated_mount=True` (default), jawm automatically mounts:

- the process `logs_directory`
- detected paths from `mk.*` variables
- detected paths from `map.*` variables

This is mainly useful when using `environment="docker"` or `environment="apptainer"` / `environment="singularity"`.

_**Note**_: User-provided container options in `environment_docker` or `environment_apptainer` still apply. Automatic mounts are added in addition to those, unless the same mount is already provided manually. Not recommended to use `False`, if it is not necessary.

**Example:**
```python
automated_mount=True
```

**YAML Example:**
```yaml
automated_mount: true
```
---

## `env`

- **Category**: `parameter`
- **Type**: `dict`

Environment variables for the `Process`.

`env` is merged into the process environment and made available during execution. It can be used to define variables needed by the script itself, or by the selected runtime environment such as local execution, Docker, Apptainer, Slurm, or Kubernetes.

For `local` execution, jawm combines the current host environment with the values from `env`, where keys in `env` override existing environment variables with the same name.

For containerized execution:

- with `environment="docker"` → variables are passed using `docker run -e`
- with `environment="apptainer"` / `environment="singularity"` → variables are passed using `apptainer exec --env`
- with `manager="kubernetes"` → variables are added to the container `env` section of the generated Job manifest

_**Note**_: `env` is a dict-like parameter, so it is **merged** across configuration layers. If the same key is defined more than once, the higher-precedence value overrides the lower-precedence one.

**Example:**
```python
env={
    "THREADS": "4",
    "MODE": "test"
}
```

**YAML Example:**
```yaml
env:
  THREADS: "4"
  MODE: "test"
```

**Example of `env` usage in script:**
```python
script="""#!/bin/bash
echo "THREADS=${THREADS}"
echo "MODE=${MODE}"
"""
```

**Python Example:**
```python
import jawm

p = jawm.Process(
    name="env_example",
    script="""#!/bin/bash
echo "THREADS=${THREADS}"
echo "MODE=${MODE}"
""",
    env={
        "THREADS": "4",
        "MODE": "test"
    }
)
```

**Merge and override behavior**

```python
# lower-precedence values
env={"THREADS": "4", "MODE": "test"}

# higher-precedence override
env={"THREADS": "8"}
```

Effective merged value:

```python
{"THREADS": "8", "MODE": "test"}
```

**CLI Example:**

Environment variables can also be injected or overridden from the CLI using `--global.env.<key>=<value>` or `--process.<process_name>.env.<key>=<value>`.

```bash
jawm module.py --global.env.THREADS="4"
```

```bash
jawm module.py --process.my_process.env.MODE="test"
```

---

## `when`

- **Category**: `parameter`
- **Type**: `bool` or `callable`
- **Default**: `True`

Conditional control for whether the `Process` should execute.

If `when` evaluates to `False`, jawm skips the process and marks it as finished without running the script.

`when` can be:

- a **boolean**
- a **callable** returning a boolean
- a **callable** that accepts the current `Process` instance as its only argument

**Example with boolean:**
```python
when=False
```

**YAML Example:**
```yaml
when: false
```

**Example with a callable:**
```python
when=lambda: os.path.exists("input.txt")
```

**Example with a callable using the current process instance:**
```python
when=lambda p: p.manager == "slurm"
```

**Full Python Example:**
```python
import os
import jawm

p = jawm.Process(
    name="run_if_input_exists",
    script="""#!/bin/bash
echo "Input exists, running process"
""",
    when=lambda: os.path.exists("input.txt")
)
```

**Full Python Example with process instance:**
```python
import jawm

p = jawm.Process(
    name="run_only_on_slurm",
    script="""#!/bin/bash
echo "Running on Slurm"
""",
    manager="slurm",
    when=lambda p: p.manager == "slurm"
)
```

**Example with a callable and no arguments:**
```python
when=lambda: os.path.exists("input.txt")
```

This runs the process only if `input.txt` exists in the current working directory.

**Example using process `var`:**
```python
when=lambda p: p.var.get("run_step", "false") == "true"
```

This runs the process only if the process variable `run_step` is set to `"true"`.

**Example using a Process instance parameter:**
```python
when=lambda p: os.path.exists(f"{p.project_directory}/inputs/sample.txt")
```

This runs the process only if `sample.txt` exists inside the process project directory.



_**Note**_: If `when` is a callable, it must accept either:

- no arguments, or
- exactly one argument, which is the current `Process` instance

If evaluation of `when` fails, jawm logs the error and skips the process.

---

## `always_run`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `False`

Whether the `Process` should still run even if a previous process has failed.

This is useful for steps such as cleanup, reporting, or notifications that should run regardless of earlier failures in the workflow.

_**Note**_: `always_run=True` does **not** override `when=False`. If the process is explicitly skipped by `when`, it will still not run.

**Example:**
```python
always_run=True
```

**YAML Example:**
```yaml
always_run: true
```

---

## `error_strategy`

- **Category**: `parameter`
- **Type**: `str`
- **Default**: `retry`
- **Allowed**: `retry`, `fail`

Controls how jawm handles a failed process execution.

- **`retry`** — jawm follows the configured `retries` behavior
- **`fail`** — jawm stops retrying immediately for that process

If `error_strategy="fail"`, jawm forces `retries=0`, even if a higher value was provided elsewhere. This parameter can be skipped entirely by just using `retries`.

_**Note**_: This parameter affects per-process failure handling, not the overall workflow structure.

**Example:**
```python
error_strategy="retry"
```

**YAML Example:**
```yaml
error_strategy: "fail"
```

In this case, jawm can retry the process according to the configured retry count.

---

## `retries`

- **Category**: `parameter`
- **Type**: `int`
- **Default**: `0`

Number of retry attempts if the `Process` fails.

If `retries=0`, jawm performs only the initial execution attempt.  
If `retries=2`, jawm can try up to **3 total attempts**:

- 1 initial attempt
- 2 retry attempts

Retries are handled by jawm for supported backends such as local, Slurm, and Kubernetes.

_**Note**_: `retries` works together with `error_strategy`. If `error_strategy="fail"`, jawm forces `retries=0`.

**Example:**
```python
retries=2
```

**YAML Example:**
```yaml
retries: 2
```

**CLI Example:**
```bash
jawm module.py --global.retries=2
```

**Process-specific CLI Example:**
```bash
jawm module.py --process.my_process.retries=2
```

---

## `retry_overrides`

- **Category**: `parameter`
- **Type**: `dict[int -> dict]`

Retry-specific parameter overrides applied on retry attempts.

`retry_overrides` lets you change selected process parameters for later attempts if the initial execution fails. The dictionary keys are **retry attempt numbers**.

For example:

- key `1` → applied before the **first retry**
- key `2` → applied before the **second retry**
- key `3` → applied before the **third retry**

This is especially useful for gradually increasing resources on retries, such as more memory, more time, or a different Slurm partition.

_**Note**_: `retry_overrides` only affects retry attempts. It does not change the initial attempt.

_**Note**_: Overrides are applied to the current process parameters for that retry. For dict-like parameters such as `manager_slurm`, matching nested keys are updated instead of replacing the whole dict.

**Example:**
```python
retry_overrides={
    1: {
        "manager_slurm": {
            "--partition": "debug",
            "--mem": "+100%"
        }
    },
    2: {
        "manager_slurm": {
            "--mem": "3.2G",
            "--time": "00:05:00"
        }
    },
    3: {
        "manager_slurm": {
            "--mem": "+1",
            "--time": "+50%"
        }
    }
}
```

**YAML Example:**
```yaml
retry_overrides:
  1:
    manager_slurm:
      --partition: "debug"
      --mem: "+100%"
  2:
    manager_slurm:
      --mem: "3.2G"
      --time: "00:05:00"
  3:
    manager_slurm:
      --mem: "+1"
      --time: "+50%"
```

**Supported override behavior**

For existing numeric-like values, jawm supports:

- **direct replacement**  
  Example: `"3.2G"` or `"00:05:00"`

- **absolute increment/decrement**  
  Example: `"+1"` or `"-2"`

- **percentage change**  
  Example: `"+50%"` or `"-25%"`

For time values already written as `HH:MM:SS`, values like `"+60"` are treated as seconds.

**Example with Slurm memory and time scaling**

```python
retry_overrides={
    1: {
        "manager_slurm": {
            "--mem": "+50%",
            "--time": "+300"
        }
    }
}
```

If the initial values were:

```python
manager_slurm={
    "--mem": "4G",
    "--time": "01:00:00"
}
```

then on the first retry, jawm would apply:

- `--mem`: `4G` → `6G`
- `--time`: `01:00:00` → `01:05:00`

**Example in a full Process**

```python
import jawm

p = jawm.Process(
    name="slurm_retry_job",
    manager="slurm",
    script="""#!/bin/bash
exit 1
""",
    retries=3,
    manager_slurm={
        "--partition": "short",
        "--mem": "4G",
        "--time": "01:00:00"
    },
    retry_overrides={
        1: {
            "manager_slurm": {
                "--partition": "debug",
                "--mem": "+100%",
                "--time": "+60"
            }
        },
        2: {
            "manager_slurm": {
                "--mem": "12G",
                "--time": "02:00:00"
            }
        }
    }
)
```

In this example:

- initial attempt uses `4G` and `01:00:00`
- first retry switches to partition `debug`, doubles memory, and adds 60 seconds
- second retry sets memory and time explicitly

_**Note**_: `retry_overrides` is most useful with parameters that already have values, especially nested dicts like `manager_slurm`. If a nested key does not already exist, jawm adds it as-is.

---

## `resume`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `False`

Whether to skip execution if a matching previous run has already completed successfully.

When `resume=True`, jawm checks the current `logs_directory` for an earlier run of the same process `name` with a matching parameter-hash prefix. If a matching run is found and its `<name>.exitcode` indicates success, jawm skips re-execution and reuses that existing run directory as the process `log_path`.

This is useful when re-running a workflow after interruption or after partial completion, since already successful steps do not need to be executed again.

_**Note**_: Resume matching is based on the process `name` and the first 6 characters of the generated process hash. The hash is derived from the effective process parameters and also includes referenced content such as `script_file`, `param_file`, and `var_file`.

_**Note**_: Resume only skips runs that completed successfully. Failed or incomplete runs are not reused.

**Example:**
```python
resume=True
```

**YAML Example:**
```yaml
resume: true
```

**CLI Example:**

Resume mode can also be enabled from the CLI using `-r` or `--resume` (this is more of a real life use case rather than per Process `resume=True`).

```bash
jawm module.py -r
```

```bash
jawm module.py --resume
```

When used from the CLI, jawm injects `resume=True` as an override for all the Processes in workflow run.

---

## `always_run`

- **Category**: `parameter`
- **Type**: `bool`
- **Default**: `False`

Whether the `Process` should still run even if one or more previous processes have failed.

This is useful for steps such as cleanup, reporting, or notifications that should run regardless of earlier failures in the workflow.

_**Note**_: `always_run=True` does not override `when=False`. If the process is explicitly skipped by `when`, it will still not run.

**Example:**
```python
always_run=True
```

**YAML Example:**
```yaml
always_run: true
```

---