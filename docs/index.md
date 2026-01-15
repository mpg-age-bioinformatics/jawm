# jawm — Just Another Workflow Manager

`jawm` is a lightweight, Python-native workflow manager for building reproducible,
dependency-aware workflows that run unchanged on laptops, HPC clusters, and Kubernetes.

It is designed for researchers, data scientists, and engineers who want the flexibility
of Python without committing to heavyweight workflow frameworks or external runtimes.

---

## Why jawm?

- Python-first  
  Workflows are plain Python modules. No DSL, no separate compiler, no runtime service.

- Local → HPC without rewrites  
  The same Process definition can run locally, on Slurm, or on Kubernetes by switching
  the execution manager.

- Reproducible by design  
  Parameter-aware content hashing ensures each process execution is uniquely identifiable.
  Optional resume logic allows skipping already completed work safely.

- Explicit dependencies and conditions  
  Express execution order using depends_on, and conditionally skip steps using when.

- Container support when you need it  
  Run steps in Docker or Apptainer while keeping native execution as the default.

- Observable and debuggable  
  Each process gets its own log directory with stdout/stderr, runtime metadata,
  monitoring files, and optional resource usage statistics.

- Configuration without magic  
  YAML-based parameter files with clear precedence rules, plus CLI and programmatic
  overrides for full control.

---

## Core concepts

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

## Quick example

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

## Execution environments

`jawm` supports multiple execution backends out of the box including Local, Slurm, Kubernetes with Containers support. Switching between them requires no changes to workflow logic.

---

## Configuration options

Processes can be configured using:
- inline Python arguments,
- YAML parameter files (global and process-specific),
- environment variable files,
- and CLI-level overrides.

All configuration sources follow explicit and documented precedence rules.

---

## When to use jawm

`jawm` is a good fit if you:
- want Python-native workflows without a separate DSL,
- work across machines and different systems,
- need reproducibility and observability,
- prefer explicit control over execution and configuration.

It is intentionally minimal and composable, leaving orchestration decisions in your hands.

---

## Project status

`jawm` is under active development.
The public API is stabilizing, but some interfaces may evolve prior to a 1.0.0 release.

---

## Next steps

Head over to Getting started to install jawm and build your first workflow module.