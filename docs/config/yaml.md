# YAML Configuration

jawm uses YAML parameter files to configure processes externally — without modifying the workflow Python code. A YAML file is a list of entries, each with a `scope` that determines how its parameters are applied.

---

## Loading a YAML File

### Via the CLI

```bash
jawm workflow.py -p params.yaml
```

### Via Python

```python
import jawm

p = jawm.Process(
    name="example",
    param_file="params.yaml"
)
```

Multiple files can be passed as a list:

```python
p = jawm.Process(
    name="example",
    script="echo hello",
    param_file=["base.yaml", "overrides.yaml"]
)
```

If `param_file` points to a directory, jawm loads all `.yaml` and `.yml` files in it (sorted alphabetically).

---

## File Structure

A jawm YAML file is a **list of entries**. Each entry is a YAML mapping (dictionary) that starts with `- scope:` to indicate how its parameters are applied.

```yaml
- scope: global
  manager: slurm
  retries: 2

- scope: process
  name: "align"
  desc: "Description of the Process align"
```

_**Note**_: Each entry **must** start with `- ` (a YAML list item). All keys within that entry are indented under it.

---

### _**Scopes**_

___

## `- scope: global`

Parameters in a `global` scope are applied to **every** process in the workflow. This is the place to set defaults that most processes share.

```yaml
- scope: global
  manager: local
  logs_directory: ./logs
  retries: 1
  var:
    THREADS: "4"
```

---

## `- scope: process`

Parameters in a `process` scope are applied only to processes whose `name` matches. The `name` field is required.

```yaml
- scope: process
  name: "align"
  manager: slurm
  manager_slurm:
    --mem: "16G"
    --time: "02:00:00"
```

Process-scoped parameters **override** global-scoped parameters for that process.

#### Wildcard matching

The `name` field supports shell-style wildcards:

```yaml
- scope: process
  name: "qc_*"
  environment: docker
  container: "python:3.11-slim"
```

This matches any process whose name starts with `qc_` (e.g., `qc_fastqc`, `qc_multiqc`).

#### Multiple names

The `name` field can also be a list, targeting several processes with the same configuration:

```yaml
- scope: process
  name:
    - "align"
    - "sort"
    - "index"
  manager: slurm
  manager_slurm:
    --partition: "partition1"
```

---

## `- scope: hash`

The `hash` scope defines a content hash policy for the workflow run. It is only used by the `jawm` CLI and does not affect Process parameters.

```yaml
- scope: hash
  include:
    - main.py
    - scripts/**/*.sh
  allowed_extensions: [py, sh]
  exclude_dirs: [__pycache__]
  exclude_files: ["*.tmp", "*.swp"]
  recursive: true
  overwrite: false
  reference: "a1b2c3d4..."
```

When present, jawm computes a content hash from the specified files and writes it to `<workflow>.hash`. If `reference` is provided, jawm validates the computed hash against it and exits with a non-zero code on mismatch.

---

## Includes

Any entry can use `includes` to import entries from other YAML files. This allows modular, reusable configuration.

### Single file

```yaml
- includes: shared/base_config.yaml

- scope: process
  name: "my_step"
  cpus: 16
```

### Multiple files

```yaml
- includes:
    - shared/slurm_defaults.yaml
    - shared/docker_settings.yaml
```

### Directory

If the include path is a directory, all `.yaml` and `.yml` files in it are loaded (sorted alphabetically):

```yaml
- includes: shared/configs/
```

### Glob patterns

```yaml
- includes: shared/*.yaml
```

### Resolution rules

- Include paths are resolved **relative to the YAML file that contains the directive**, not relative to the working directory.
- jawm detects and prevents **circular includes**.
- If an explicit include path does not exist, jawm raises an error. Glob patterns that match nothing are silently ignored.
- Included entries are inserted in place — they participate in the same global/process merge as if they were written directly in the parent file.

---

## Writing YAML Values

jawm YAML files are standard YAML loaded with `yaml.safe_load`. Below are the common patterns for different value types.

### Strings

```yaml
- scope: global
  manager: local
  container: "python:3.11-slim"
  logs_directory: ./logs
```

Quotes are optional for simple strings but recommended when the value contains special characters.

### Numbers

```yaml
- scope: global
  retries: 3
```

YAML parses unquoted numbers as integers or floats. jawm will use them as-is.

### Booleans

```yaml
- scope: process
  name: "step1"
  resume: true
  parallel: false
  when: true
```

YAML recognizes `true`/`false`, `yes`/`no`, `on`/`off` as booleans (unquoted).

### Multi-line strings (scripts)

Use the YAML block scalar `|` to write multi-line content such as scripts:

```yaml
- scope: process
  name: "hello"
  script: |
    #!/bin/bash
    echo "Hello from jawm"
    echo "Done"
```

The `|` preserves newlines exactly as written. Each line must be indented under `script:`.

### Dictionaries

Dictionaries can be written in **expanded** or **inline** form.

**Expanded** (recommended for readability):

```yaml
- scope: global
  env:
    THREADS: "4"
    PATH: "/usr/local/bin"
  manager_slurm:
    --mem: "4G"
    --time: "01:00:00"
    --partition: "dedicated"
```

**Inline** (flow style):

```yaml
- scope: global
  env: {"THREADS": "4", "PATH": "/usr/local/bin"}
  manager_slurm: {"--mem": "4G", "--time": "01:00:00"}
```

Both forms are equivalent. Expanded form is preferred for complex or nested values.

### Nested dictionaries

```yaml
- scope: process
  name: "k8_job"
  manager_kubernetes:
    namespace: "production"
    resources:
      requests:
        cpu: "500m"
        memory: "1Gi"
      limits:
        cpu: "2"
        memory: "4Gi"
```

### Lists

Lists can be written in **expanded** or **inline** form.

**Expanded**:

```yaml
- scope: process
  name: "step2"
  depends_on:
    - "step1a"
    - "step1b"
```

**Inline** (flow style):

```yaml
- scope: process
  name: "step2"
  depends_on: ["step1a", "step1b"]
```

### Mixed dictionaries and lists

```yaml
- scope: process
  name: "k8_mount_test"
  manager_kubernetes:
    namespace: "jawm"
    mounts:
      - name: "ref"
        mode: "pvc"
        claimName: "ref-data"
        mountPath: "/ref"
        readOnly: true
      - name: "scratch"
        mode: "pvc"
        claimName: "scratch"
        mountPath: "/scratch"
        readOnly: false
```

Here `mounts` is a list of dictionaries — each item starts with `- ` and contains key-value pairs indented under it.

---

## Deep-Merged Parameters

When the same dict-type parameter appears in multiple places (e.g., both global and process scope), jawm **deep-merges** them rather than replacing the entire dictionary. The following parameters are deep-merged:

`var`, `env`, `manager_local`, `manager_slurm`, `manager_kubernetes`, `inputs`, `outputs`, `environment_docker`, `environment_apptainer`, `retry_overrides`

Example:

```yaml
- scope: global
  manager_slurm:
    --partition: "general"
    --mem: "4G"

- scope: process
  name: "heavy_step"
  manager_slurm:
    --mem: "32G"
    --time: "08:00:00"
```

The resulting `manager_slurm` for `heavy_step` is:

```yaml
--partition: "general"   # from global
--mem: "32G"             # overridden by process
--time: "08:00:00"       # added by process
```

All other parameters (strings, numbers, booleans, lists) are **replaced** entirely by the higher-precedence scope.

---

## Precedence

When parameters are defined in multiple places, higher-precedence values override lower-precedence ones. The full precedence order depends on how the YAML file is loaded.

### Normal usage (Python `param_file`)

```text
default_parameters < YAML global < YAML process < kwargs < python_args < override_parameters
```

Python arguments override YAML.

### CLI-driven usage (`jawm workflow.py -p params.yaml`)

```text
default_parameters < kwargs < python_args < YAML global < YAML process < CLI overrides < override_parameters
```

When a parameter file is supplied through the CLI, jawm assumes the workflow is **configuration-driven**, so YAML overrides Python arguments.

### CLI overrides

The CLI supports direct parameter injection that overrides both YAML and Python values:

```bash
# Global override (applies to all processes)
jawm workflow.py -p params.yaml --global.retries=5

# Process-specific override
jawm workflow.py -p params.yaml --process.align.manager=local

# Nested parameter override
jawm workflow.py -p params.yaml --process.align.manager_slurm.--mem=64G
```

See [Configuration & Precedence](../process/conf_precedence.md) for the complete precedence breakdown.

---

## Example

A single YAML file combining global defaults, process-specific configuration, includes, and various value types:

```yaml
# Load shared base configuration
- includes: shared/base.yaml

# Global defaults for all processes
- scope: global
  manager: slurm
  logs_directory: ./logs
  retries: 2
  env:
    THREADS: "4"
  manager_slurm:
    --partition: "general"
    --mem: "4G"
    --time: "01:00:00"

# QC processes: run locally in Docker
- scope: process
  name: "qc_*"
  manager: local
  environment: docker
  container: "biocontainers/fastqc:0.12.1"

# Alignment: heavier resources on Slurm
- scope: process
  name: "align"
  manager_slurm:
    --mem: "32G"
    --time: "08:00:00"
    --cpus-per-task: "16"
  env:
    THREADS: "16"

# Multiple processes sharing the same config
- scope: process
  name:
    - "sort"
    - "index"
    - "markdup"
  manager_slurm:
    --mem: "16G"
    --time: "02:00:00"
  var:
    mk.output_folder: './test/test-output/'
    algorithm: "kruskal"

# Variant calling with retry escalation
- scope: process
  name: "call_variants"
  retries: 3
  retry_overrides:
    1:
      manager_slurm:
        --mem: "+100%"
        --time: "+60"
    2:
      manager_slurm:
        --mem: "64G"
        --time: "12:00:00"
```
