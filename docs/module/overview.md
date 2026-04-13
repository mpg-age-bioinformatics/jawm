# Module Overview

A jawm **module** is a reusable, shareable unit of workflow code. Concretely, a module is a single Python file — usually accompanied by a script(s) and YAML file(s) — that defines one or more named sub-workflows and exposes them through a small command-line interface.

Modules are how jawm turns one-off workflows into building blocks you can run on their own, share across projects, publish as Git repositories, and compose into larger pipelines.

---

### The mental model

If a [`Process`](../process/overview.md) is a single step (a bash/Python/R script that runs somewhere with some configuration), then a module is **a collection of Processes, grouped by purpose, that a user can invoke by name from the command line**.

A module answers three questions for whoever runs it:

1. **What can this module do?** — the list of sub-workflows it exposes (e.g. `main`, `sra`, `test`).
2. **Which of those should I run?** — chosen via positional CLI arguments.
3. **With what parameters?** — supplied via YAML parameter and variable files (`-p`, `-v`).

Everything else — scripts, container images, scheduler backends, dependencies between Processes — is an internal implementation detail of the module.

---

### Why modules?

Modules exist for four practical reasons:

- **Reuse across pipelines.** An alignment module written once can be called from every downstream pipeline that needs alignment, without copy-pasting `Process` definitions.
- **Composition.** A parent workflow can load several modules and orchestrate them together. Each module stays focused on its own domain while the parent handles wiring.
- **Sharing.** Modules published as Git repositories can be pulled on demand via [`jawm.utils.load_modules()`](../utils.md#load_modules), locked to a specific branch, tag, or commit.
- **Testability.** The convention of giving every module a dedicated `test` sub-workflow makes it easy to verify that a module still works in a new environment before trusting it in production.

---

### Anatomy of a module

A minimal module is a single `.py` file. A typical one looks more like this:

```
my_module/
├── my_module.py        # Process definitions + CLI entry point
├── submodules (optional)
│   ├── submodule1.py
    ├── submodule2.py
└── yaml/               # Optional default parameter YAMLs
    └── docker.yaml
```

_**Note**_: Nothing in jawm requires this directory layout. It's just the convention used across published jawm modules, and it makes modules easier to read at a glance.

---

### Two ways to use a module

Once a module exists, there are two ways to put it to work:

- **Standalone.** Invoke the module file (local or remote) directly from the shell: `python qc.py -p params.yaml`. This is the easiest way to develop, test, and run a single module.
- **Composed.** From a parent Python file, call `jawm.utils.load_modules([...])` to pull in one or more modules (local or remote) and then orchestrate them together. The parent becomes the conductor; each loaded module contributes its own Processes.

Both modes are covered in detail on the [Load & Use Modules](load_use.md) page.

---

### Conventions

These aren't enforced by jawm — they're community conventions that make modules predictable for anyone consuming them:

- **`main`** — run every sub-workflow the module knows about. Every sub-workflow's gate should include `"main"` so that `python mod.py main` acts as "do everything".
- **`test`** — a lightweight sanity check that requires no real data, just enough to confirm the module is wired correctly (scripts exist, container pulls, etc.).
- Other sub-workflow names are free-form and typically describe what they do (e.g. `bwa`, `sra`, `align`, `call_variants`, `geo`).
- Modules published as Git repositories conventionally use the `jawm_<name>` repository prefix — e.g. [`jawm_demo`](https://github.com/mpg-age-bioinformatics/jawm_demo), `jawm_bwa`, `jawm_sra`. Browse the published set at [github.com/mpg-age-bioinformatics](https://github.com/mpg-age-bioinformatics?q=jawm_&type=all).

---

### Where to go next

- **[Load & Use Modules](load_use.md)** — running modules standalone, loading them from Git with `jawm.utils.load_modules()`, pinning to specific refs, the `JAWM_MODULES_PATH` environment variable, and composing multiple modules in a single parent workflow.
- **[Develop a Module](develop.md)** — writing your own module from scratch: the skeleton, the `parse_arguments()` / `workflow()` idiom, exposing parameters via `var`, adding custom CLI flags, directory layout, and how to give your module a good `test` sub-workflow.
