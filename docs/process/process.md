# Process

The **`Process`** class is the core abstraction in **jawm**.  
A workflow in jawm is a Python script that defines one or more `Process` objects and executes them. Each `Process` represents a **single computational task**, such as running a script, or launching a containerized/slurm job.

Processes can be chained together through dependencies to form a complete workflow.

---

# What is a Process?

A `Process` represents a **unit of work** primarily with:

- a **name**
- a **script or command to execute**
- optional **dependencies** and **conditional execution**
- configurable **execution environment**
- configurable **execution backend** such as local, Slurm, or Kubernetes
- optional **variables and parameters**

A minimal workflow may consist of a single process, while complex workflows can contain many processes with dependencies.

Example:

\`\`\`python
import jawm

p = jawm.Process(
    name="hello_world",
    script="""#!/bin/bash
echo "Hello from jawm"
"""
)

p.execute()
\`\`\`

When executed, jawm will:

1. Resolve configuration parameters
2. Prepare the execution environment
3. Execute the script using the selected backend
4. Store logs and metadata

---

# Basic Example

A simple workflow with two dependent processes:

\`\`\`python
import jawm

step1 = jawm.Process(
    name="download",
    script="""#!/bin/bash
echo "Downloading data"
"""
)

step2 = jawm.Process(
    name="process",
    script="""#!/bin/bash
echo "Processing data"
""",
    depends_on=[step1]
)

step1.execute()
step2.execute()
\`\`\`

Here:

- `step2` will wait until `step1` finishes successfully.
- jawm ensures dependency order automatically.

---

# Process Configuration

A `Process` can be configured using several mechanisms:

1. **YAML configuration files**
2. **Python keyword arguments**
3. **Explicit Python arguments**
4. **CLI overrides**
5. **Class default parameters**

These configuration layers are merged with a defined **precedence order**.

---

# Parameter Precedence

jawm supports flexible configuration through multiple layers.  
When parameters are defined in multiple places, **higher-precedence values override lower-precedence ones**.

### Standard precedence (low \u2192 high)

\`\`\`text
default_parameters
< YAML global
< YAML process
< kwargs
< python_args
< (CLI -p) YAML global
< (CLI -p) YAML process
< cli injected override (--global)
< cli injected override (--process)
< override_parameters
\`\`\`

This allows workflows to be configured in a structured way while still supporting runtime overrides.

---

# Internal Precedence Logic

The parameter precedence changes slightly depending on whether a YAML parameter file is provided through the CLI using `-p`.

## Normal Usage

When no CLI parameter file override is used:

\`\`\`text
default_parameters
< YAML global
< YAML process
< kwargs
< explicit_args
< cli injected override (--global)
< cli injected override (--process)
< override_parameters
\`\`\`

In this mode, **Python arguments override YAML parameters**.

Internally, the precedence layers are applied as:

\`\`\`python
_precedence_layers = [
    self.__class__.default_parameters,
    global_params,
    process_params,
    kwargs,
    explicit_args,
    cli_global,
    cli_proc_block,
    self.__class__.override_parameters
]
\`\`\`

---

## CLI-driven Usage

When a parameter file is supplied through the CLI with `-p`, jawm assumes the workflow is **configuration-driven**, so **YAML overrides Python arguments**.

\`\`\`text
default_parameters
< kwargs
< explicit_args
< YAML global
< YAML process
< cli injected override (--global)
< cli injected override (--process)
< override_parameters
\`\`\`

Internally, the precedence layers become:

\`\`\`python
_precedence_layers = [
    self.__class__.default_parameters,
    kwargs,
    explicit_args,
    global_params,
    process_params,
    cli_global,
    cli_proc_block,
    self.__class__.override_parameters
]
\`\`\`

Detection is done automatically:

\`\`\`python
_cli_paramfile = bool(self.__class__.override_parameters.get("param_file"))
\`\`\`

---

# Ways to Configure a Process

## 1. Python Arguments

The most common method is to provide parameters directly:

\`\`\`python
import jawm

p = jawm.Process(
    name="example",
    script="""#!/bin/bash
echo "Hello"
""",
    manager="local",
    retry=2
)
\`\`\`

---

## 2. YAML Configuration

Processes can also read configuration from YAML files.

Example of a global YAML block:

\`\`\`yaml
scope: global

manager: slurm
retry: 2
\`\`\`

Example of a process-specific YAML block:

\`\`\`yaml
scope: process

process: example
retry: 5
\`\`\`

---

## 3. CLI Overrides

Parameters can also be overridden directly from the CLI.

Example:

\`\`\`bash
jawm run workflow.py --process.example.retry=5
\`\`\`

Global override example:

\`\`\`bash
jawm run workflow.py --global.retry=3
\`\`\`

---

# Process Execution

A process is executed using:

\`\`\`python
p.execute()
\`\`\`

During execution, jawm typically performs several steps:

1. **Parameter resolution**
2. **Variable expansion**
3. **Dependency validation**
4. **Run directory creation**
5. **Script execution**
6. **Logging and monitoring**

---

# Execution Backends

jawm supports multiple execution managers:

| Backend | Description |
|---|---|
| `local` | Execute directly on the local machine |
| `slurm` | Submit jobs to a Slurm cluster |
| `kubernetes` | Run jobs inside a Kubernetes cluster |

The manager can be configured per process.

Example:

\`\`\`python
import jawm

p = jawm.Process(
    name="align",
    script="""#!/bin/bash
./align.sh
""",
    manager="slurm"
)
\`\`\`

---

# Execution Environments

Processes may also run inside containers.

Supported container systems include:

- Docker
- Apptainer / Singularity

Example:

\`\`\`python
import jawm

p = jawm.Process(
    name="analysis",
    script="""#!/bin/bash
./run_analysis.sh
""",
    apptainer="analysis.sif"
)
\`\`\`

---

# Dependencies

Processes can depend on other processes.

Example:

\`\`\`python
import jawm

step1 = jawm.Process(
    name="prepare",
    script="""#!/bin/bash
echo "Preparing input"
"""
)

step2 = jawm.Process(
    name="run",
    script="""#!/bin/bash
echo "Running analysis"
""",
    depends_on=[step1]
)
\`\`\`

jawm will:

- wait for dependencies
- ensure successful completion
- prevent execution if dependencies fail

---

# Variables

Processes support variable substitution.

Example:

\`\`\`python
import jawm

p = jawm.Process(
    name="example",
    script="""#!/bin/bash
echo "{{sample}}"
""",
    var={"sample": "test"}
)
\`\`\`

This becomes:

\`\`\`bash
echo "test"
\`\`\`

Variables may also be loaded from files using `var_file`.

---

# Logs/Run Directories

Each process execution creates a **logs/run directory** that stores:

- command script
- stdout logs
- stderr logs
- metadata
- process state

This supports:

- workflow reproducibility
- resume functionality
- easier debugging

---

# Resume and Retry

Processes support:

- automatic **resume**
- configurable **retry attempts**

Example:

\`\`\`python
import jawm

p = jawm.Process(
    name="step",
    script="""#!/bin/bash
echo "Running step"
""",
    retry=3,
    resume=True
)
\`\`\`

---
