# jawm — Just Another Workflow Manager

`jawm` is a lightweight, Python-native workflow manager for building reproducible, dependency-aware workflows across different execution environments.

It is designed for researchers, data scientists, and engineers who want the flexibility of Python without committing to a heavyweight workflow framework, a custom DSL, or an external orchestration service.

---

### Why jawm?

- 🐍 **Python-native**   
  Workflows are plain Python modules. No DSL, no separate compiler, no runtime service.

- 🔁 **Same workflow, different backends**  
  Switch between local, Slurm, and Kubernetes execution without rewriting workflow logic.

- 🪶 **Lightweight by intention**  
  jawm stays minimal and composable, leaving workflow structure and control in your hands.

- 🧩 **Simple abstraction**  
  One core concept — `Process` — to define and run workflow steps.

- ⚙️ **Flexible configuration**  
  Configure processes with Python arguments, YAML parameter files, and CLI overrides.

- ♻️ **Reproducible by design**  
  Each process execution gets a parameter-aware hash and its own run directory.

- 🔗 **Explicit workflow control**  
  Manage execution order, conditional runs, resumeability, and so on.

- 📦 **Container support when needed**  
  Run processes in Docker or Apptainer along with the native execution.

- 🔍 **Observable and easy to debug**  
  Each run stores logs, generated scripts, commands, exit codes, and runtime metadata.

---

### Core concepts

At its core, jawm is built around a single abstraction:

`Process`

A Process represents one step in a workflow:

- it executes a script (inline or from a file),
- has parameters, which control what runs, and how it runs,
- can depend on other processes,
- and runs using a selectable execution backend.

A workflow is simply a Python module that defines one or more Process objects and
triggers them based on the definations.

---

### Quick example

```python
import jawm

p = jawm.Process(
    name="hello_world",
    script="""#!/bin/bash
echo "Hello from jawm"
"""
)

p.execute()
```

That’s it.

This process will:

- generate a unique hash,
- create a dedicated log directory,
- execute locally by default,
- and record its execution state.

---

### Execution environments

`jawm` supports multiple execution backends out of the box including Local, Slurm, Kubernetes with Containers support. Switching between them requires no changes to workflow logic.

---

### Configuration options

Processes can be configured using:

- inline Python arguments,
- YAML parameter files (global and process-specific),
- jawm config or environment variables files,
- and CLI-level overrides.

All configuration sources follow explicit and documented precedence rules.

---

### When to use jawm

`jawm` is a good fit if you:

- want Python-native workflows without a separate DSL,
- work across machines and different systems,
- need reproducibility and observability,
- prefer explicit control over execution and configuration.

It is intentionally minimal and composable, leaving orchestration decisions in your hands.

---

### Project status

`jawm` is under active development.
The public API is stabilizing, but some interfaces may evolve prior to a 1.0.0 release.

---
