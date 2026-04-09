# YAML Configuration

jawm uses YAML parameter files to configure processes externally — without modifying the workflow Python code. A YAML file is a list of entries, each with a `scope` that determines how its parameters are applied.

---

## Loading a YAML File

### Via the CLI

```bash
jawm workflow.py -p params.yaml
```

Multiple files can be passed in a single `-p` flag:

```bash
jawm workflow.py -p base.yaml overrides.yaml
```

When multiple files are provided, they are processed **in order** — later files override earlier ones for the same scope and parameter. For example, if `base.yaml` sets `retries: 1` globally and `overrides.yaml` sets `retries: 3` globally, the final value is `3`.

A directory can also be passed. jawm loads all `.yaml` and `.yml` files in it, sorted alphabetically:

```bash
jawm workflow.py -p parameters/
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
    param_file=["base.yaml", "overrides.yaml"]
)
```

The same ordering rule applies — later files in the list take precedence over earlier ones.

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

_**Note**_: Each entry **must** start with `- ` (a YAML list item). All keys within that entry are indented under it. Also, it is possible to include non-jawm relevant content in the same YAML; jwam would only consider the relevant part on that case.

---

### _**Scopes**_

___

## `- scope: global`

Parameters in a `global` scope are applied to **every** process in the workflow. This is the place to set shared defaults — execution backend, resource requests, environment variables, and script variables — so that individual processes only need to specify what is different.

Any parameter that can be passed to `jawm.Process()` can be set in a global scope entry. If the same parameter also appears in a `process` scope, the process-scoped value takes precedence.

#### Minimal example

```yaml
- scope: global
  manager: local
  logs_directory: ./logs
```

#### With more parameters

```yaml
- scope: global
  manager: slurm
  logs_directory: ./logs
  retries: 2
  var:
    THREADS: "4"
    GENOME: "hg38"
    mk.OUTPUT_DIR: "./results"
  env:
    OMP_NUM_THREADS: "4"
  manager_slurm:
    --partition: "general"
    --mem: "4G"
    --time: "01:00:00"
```

#### Multiple global entries

A YAML file/ multiple YAMLs can contain more than one `global` entry. They are merged in order — later entries override earlier ones for the same keys:

```yaml
- scope: global
  retries: 1
  manager: local

- scope: global
  retries: 3
```

The final global value of `retries` is `3`.

---

## `- scope: process`

Parameters in a `process` scope are applied only to processes whose `name` matches. The `name` field is **required** — it tells jawm which process(es) this block applies to.

Process-scoped parameters **override** global-scoped parameters for that process. Any parameter that can be passed to `jawm.Process()` can be used here.

#### Basic example

```yaml
- scope: process
  name: "align"
  manager: slurm
  manager_slurm:
    --mem: "16G"
    --time: "02:00:00"
    --cpus-per-task: "8"
  var:
    THREADS: "8"
    REFERENCE: "/data/genomes/hg38.fa"
```

If the global scope also defines `var`, the two are **deep-merged** — so the process gets both the global variables and its own `THREADS` and `REFERENCE` (with `THREADS` overriding the global value if it was set there).

#### Example with script

A process scope can include the full script content, making it possible to define an entire process purely in YAML:

```yaml
- scope: process
  name: "greet"
  script: |
    #!/bin/bash
    echo "Hello, {{USER_NAME}}!"
    echo "Project: {{PROJECT}}"
  var:
    USER_NAME: "Alice"
    PROJECT: "jawm_demo"
```

The corresponding Python code only needs:

```python
import jawm

p = jawm.Process(name="greet")
p.execute()
```

And thne can be executed with `jawm -p params.yaml`.

#### Wildcard matching

The `name` field supports shell-style wildcards (`*`, `?`, `[...]`), allowing a single block to target multiple processes by pattern:

```yaml
- scope: process
  name: "qc_*"
  environment: docker
  container: "python:3.11-slim"
```

This matches any process whose name starts with `qc_` (e.g., `qc_fastqc`, `qc_multiqc`).

```yaml
- scope: process
  name: "step_?"
  retries: 2
```

This matches `step_1`, `step_2`, `step_a`, etc. — any single character after `step_`.

#### Multiple names

The `name` field can also be a list, targeting several specific processes with the same configuration:

```yaml
- scope: process
  name:
    - "align"
    - "sort"
    - "index"
  manager: slurm
  manager_slurm:
    --partition: "partition1"
    --mem: "16G"
  var:
    THREADS: "8"
```

#### Multiple process entries for the same name

Multiple process scope entries can target the same process. They are merged in order:

```yaml
- scope: process
  name: "align"
  manager: slurm
  retries: 2

- scope: process
  name: "align"
  manager_slurm:
    --mem: "32G"
```

The process `align` gets both `retries: 2` and `--mem: "32G"`.

---

## `- scope: hash`

The `hash` scope defines a **content hash policy** for the workflow run. It is only used by the `jawm` CLI and does not affect Process parameters.

When jawm encounters a `scope: hash` entry, it computes a SHA-256 hash from the specified files and writes it to `<logs_directory>/jawm_hashes/<workflow>.hash`. This allows you to detect whether the inputs to a workflow run have changed between runs.

#### Required field

- **`include`** — list of files, directories, or glob patterns to hash. This is the only required field.

#### Optional fields

| Field | Type | Default | Description |
|---|---|---|---|
| `allowed_extensions` | list of str | all files | Only hash files with these extensions (e.g., `[py, sh]`) |
| `exclude_dirs` | list of str | none | Skip directories matching these patterns (e.g., `[__pycache__, .git]`) |
| `exclude_files` | list of str | none | Skip files matching these patterns (e.g., `["*.tmp", "*.swp"]`) |
| `recursive` | bool | `true` | Whether to recurse into subdirectories |
| `overwrite` | bool | `false` | Whether to overwrite the hash file if it already exists |
| `reference` | str | none | A hex hash string or path to a file containing a hash, used for validation |

#### Minimal example

Hash only the workflow script and its parameter file:

```yaml
- scope: hash
  include:
    - workflow.py
    - params.yaml
```

#### With filters

Hash all Python and shell scripts, excluding temporary files and cache directories:

```yaml
- scope: hash
  include:
    - "."
  allowed_extensions: [py, sh, yaml]
  exclude_dirs: [__pycache__, .git, logs]
  exclude_files: ["*.tmp", "*.swp", "*.pyc"]
```

#### With glob patterns

```yaml
- scope: hash
  include:
    - main.py
    - scripts/**/*.sh
    - config/*.yaml
```

Glob patterns follow standard shell glob syntax. `**` matches any number of directories.

#### Reference validation

The `reference` field allows jawm to compare the computed hash against a known value. If the hashes do not match, jawm exits with code `73` (`EXIT_HASH_REFERENCE_MISMATCH`).

The reference can be a literal SHA-256 hex string:

```yaml
- scope: hash
  include:
    - workflow.py
    - params.yaml
  reference: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
```

Or a path to a file that contains the expected hash (first non-empty line is read):

```yaml
- scope: hash
  include:
    - workflow.py
    - params.yaml
  reference: "expected_hashes/workflow.hash"
```

This is useful for CI or production environments where you want to ensure that the workflow inputs have not been modified.

#### Output files

When `scope: hash` is present, jawm writes two files under `<logs_directory>/jawm_hashes/`:

- **`<workflow>.hash`** — the computed SHA-256 content hash
- **`<workflow>_user_defined.history`** — an append-only log of hash values from each run

_**Note**_: jawm also always writes `<workflow>_input.history` (an automatic run hash) regardless of whether `scope: hash` is present. The `scope: hash` feature provides additional user-defined content hashing on top of that.

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

## Examples

### 1. Script-in-YAML with minimal Python

The YAML file defines everything — script, variables, and configuration. The Python code only creates the process by name.

`params.yaml`:

```yaml
- scope: global
  logs_directory: ./logs

- scope: process
  name: "greet"
  script: |
    #!/bin/bash
    echo "Hello, {{USER_NAME}}!"
    echo "Running project: {{PROJECT}}"
    echo "Output goes to: {{OUTPUT_DIR}}"
    mkdir -p {{OUTPUT_DIR}}
    echo "done" > {{OUTPUT_DIR}}/status.txt
  var:
    USER_NAME: "Alice"
    PROJECT: "demo"
    OUTPUT_DIR: "./results"
```

`workflow.py`:

```python
import jawm

p = jawm.Process(name="greet")
p.execute()
```

Run with:
```bash
jawm workflow.py -p params.yaml
```

---

### 2. Global defaults with process overrides

`params.yaml`:

```yaml
- scope: global
  manager: slurm
  logs_directory: ./logs
  retries: 2
  var:
    THREADS: "4"
    GENOME: "hg38"
  env:
    OMP_NUM_THREADS: "4"
  manager_slurm:
    --partition: "general"
    --mem: "4G"
    --time: "01:00:00"

- scope: process
  name: "align"
  var:
    THREADS: "16"
    REFERENCE: "/data/genomes/hg38.fa"
  manager_slurm:
    --mem: "32G"
    --time: "08:00:00"
    --cpus-per-task: "16"

- scope: process
  name: "call_variants"
  var:
    CALLER: "gatk"
    MIN_QUAL: "30"
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

`workflow.py`:

```python
import jawm

align = jawm.Process(
    name="align",
    param_file="params.yaml",
    script="""#!/bin/bash
bwa mem -t {{THREADS}} {{REFERENCE}} reads_R1.fq.gz reads_R2.fq.gz > aligned.sam
"""
)

call = jawm.Process(
    name="call_variants",
    param_file="params.yaml",
    script="""#!/bin/bash
{{CALLER}} HaplotypeCaller -R {{REFERENCE}} -I aligned.bam --min-base-quality-score {{MIN_QUAL}} -O variants.vcf
""",
    depends_on=[align]
)

align.execute()
call.execute()
```

The process `align` inherits `GENOME: "hg38"` from global and gets `THREADS: "16"` from its process scope (overriding the global `"4"`). The `manager_slurm` dicts are deep-merged, so `align` gets `--partition: "general"` from global plus `--mem: "32G"`, `--time: "08:00:00"`, and `--cpus-per-task: "16"` from its process scope.

---

### 3. Docker execution with script in YAML

`docker_params.yaml`:

```yaml
- scope: global
  environment: docker
  container: "python:3.11-slim"

- scope: process
  name: "analyze"
  script: |
    #!/usr/bin/env python3
    import os
    data_path = os.environ.get("DATA_PATH", "/data")
    sample = "{{SAMPLE_ID}}"
    print(f"Analyzing sample {sample} from {data_path}")
    with open(f"output_{sample}.txt", "w") as f:
        f.write(f"Results for {sample}\n")
  var:
    SAMPLE_ID: "S001"
  env:
    DATA_PATH: "/data"
```

`workflow.py`:

```python
import jawm

p = jawm.Process(name="analyze")
p.execute()
```

Run with:
```bash
jawm workflow.py -p docker_params.yaml
```

---

### 4. Wildcard and multi-name targeting

`params.yaml`:

```yaml
- scope: global
  manager: slurm
  logs_directory: ./logs
  var:
    GENOME: "hg38"
    DATA_DIR: "./data"

# All QC steps share the same container
- scope: process
  name: "qc_*"
  environment: docker
  container: "biocontainers/fastqc:0.12.1"
  manager: local

# Multiple post-processing steps share the same Slurm resources
- scope: process
  name:
    - "sort"
    - "index"
    - "markdup"
  manager_slurm:
    --mem: "16G"
    --time: "02:00:00"
  var:
    OUTPUT_DIR: "./results/processed"
```

---

### 5. Includes and modular configuration

`base.yaml` (shared defaults):

```yaml
- scope: global
  manager: slurm
  logs_directory: ./logs
  retries: 1
  manager_slurm:
    --partition: "general"
    --mem: "4G"
    --time: "01:00:00"
```

`docker.yaml` (shared Docker settings):

```yaml
- scope: global
  environment: docker
  container: "python:3.11-slim"
```

`params.yaml` (main configuration):

```yaml
- includes:
    - shared/base.yaml
    - shared/docker.yaml

- scope: process
  name: "train_model"
  var:
    EPOCHS: "100"
    LEARNING_RATE: "0.001"
    MODEL_DIR: "./models"
  manager_slurm:
    --mem: "64G"
    --time: "12:00:00"
    --gres: "gpu:1"
  script: |
    #!/usr/bin/env python3
    print("Training for {{EPOCHS}} epochs, lr={{LEARNING_RATE}}")
    print("Saving model to {{MODEL_DIR}}")
```

`workflow.py`:

```python
import jawm

p = jawm.Process(name="train_model", param_file="params.yaml")
p.execute()
```

---

### 6. Slurm with Apptainer container

`params.yaml`:

```yaml
- scope: global
  manager: slurm
  environment: apptainer
  container: "docker://python:3.11-slim"
  logs_directory: ./logs
  manager_slurm:
    --time: "00:30:00"
    --mem: "2G"
    --cpus-per-task: "2"

- scope: process
  name: "compute"
  var:
    INPUT: "./data/input.csv"
    OUTPUT: "./results/output.csv"
    ALGORITHM: "pca"
  script: |
    #!/usr/bin/env python3
    print("Processing {{INPUT}} with {{ALGORITHM}}")
    print("Writing to {{OUTPUT}}")
```

---

### 7. Kubernetes with workspace and mounts

`k8s_params.yaml`:

```yaml
- scope: global
  manager: kubernetes
  manager_kubernetes:
    namespace: "production"
    backoffLimit: 0
    ttlSecondsAfterFinished: 120
    resources:
      requests:
        cpu: "100m"
        memory: "128Mi"

- scope: process
  name: "k8_job"
  manager_kubernetes:
    workspace:
      claimName: "project-data"
      mountPath: "/work"
      subPath: "analysis"
      readOnly: false
      mkdir: true
    mounts:
      - name: "reference"
        mode: "pvc"
        claimName: "ref-data"
        mountPath: "/ref"
        readOnly: true
    resources:
      requests:
        cpu: "2"
        memory: "8Gi"
  var:
    REF_GENOME: "/ref/hg38.fa"
    WORK_DIR: "/work"
  script: |
    #!/bin/bash
    echo "Reference: {{REF_GENOME}}"
    echo "Working in: {{WORK_DIR}}"
    ls {{WORK_DIR}}
```

---

### 8. Content hashing for reproducibility

`params.yaml`:

```yaml
- scope: global
  manager: local
  logs_directory: ./logs

- scope: process
  name: "pipeline"
  var:
    VERSION: "1.0"
  script: |
    #!/bin/bash
    echo "Pipeline version {{VERSION}}"

- scope: hash
  include:
    - workflow.py
    - params.yaml
    - scripts/
  allowed_extensions: [py, sh, yaml]
  exclude_dirs: [__pycache__, logs, .git]
  exclude_files: ["*.tmp"]
```

Run with:

```bash
jawm workflow.py -p params.yaml
```

jawm computes a SHA-256 hash from the specified files and writes it to `logs/jawm_hashes/workflow.hash`.
