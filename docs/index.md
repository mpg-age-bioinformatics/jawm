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

- 🌐 **Reusable workflow modules**  
  Run shared/remote workflow modules directly or import them into other workflows for reuse.

- 🔍 **Observable and easy to debug**  
  Each run stores logs, generated scripts, commands, exit codes, and runtime metadata.

---

### Core concepts

At its core, jawm is built around a single abstraction:

`Process`

A `Process` represents one step in a workflow. It can:

<span style="color:#2196F3; font-weight:600">→</span> execute a script (inline or from file)  
<span style="color:#2196F3; font-weight:600">→</span> define parameters that control execution  
<span style="color:#2196F3; font-weight:600">→</span> depend on other processes, or run conditionally  
<span style="color:#2196F3; font-weight:600">→</span> use a selectable execution backend

A workflow in jawm is simply a Python module that defines set of `Process` objects and executes them in the desired order.

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

This is all you need to run your first jawm process.

When executed, jawm will:

- generate a unique process hash,
- create a dedicated run log directory,
- execute the process locally by default,
- and store logs and runtime metadata.

---

### Execution environments

`jawm` supports multiple execution backends out of the box including Local, Slurm, Kubernetes with Containers support. Switching between them requires no changes to workflow logic.

---

### Configuration options

`jawm` provides multiple ways to configure processes, depending on how you prefer to build and run workflows.

A `Process` can be configured through:

- 📌 inline Python arguments
- 📌 YAML parameter files with `global` and `process` scope
- 📌 jawm config or environment variable files
- 📌 CLI-level overrides

These configuration sources follow explicit precedence rules, so it is always clear which value takes effect when the same parameter is defined in more than one place.

---

### When to use jawm

`jawm` is a good fit if you:

- 🐍 want Python-native workflows without a separate DSL
- 🌍 work across different machines and execution systems
- ♻️ need reproducible and traceable process execution
- 🔍 want clear logs, metadata, and debuggable runs
- ⚙️ prefer explicit control over execution and configuration
- 🌐 run shared or remotely available workflow modules directly with ease
- 🪶 want a lightweight workflow manager/orchestrator that stays out of your way

jawm is intentionally minimal and composable, leaving workflow structure and orchestration decisions in your hands.

---

### Project status

`jawm` is under active development.
The public API is stabilizing, but some interfaces may evolve prior to a 1.0.0 release.

---

### Next steps

Head over to Getting started to install jawm and build your first workflow module.
