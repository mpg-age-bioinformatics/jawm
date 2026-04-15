# Load Modules in Workflow

This page covers how to load and compose jawm modules from within a Python workflow using [`jawm.utils.load_modules()`](../utils.md#load_modules). This is the mechanism for building larger pipelines out of smaller, reusable modules — each module contributes its own Processes while a parent workflow handles the orchestration.

For running a module standalone from the command line, see [Run a Module](run.md).

---

### Basic usage

`load_modules()` takes a list of paths or repository specs and imports them into the calling Python file:

```python
import jawm

# Load a module from a local path (relative to this file)
jawm.utils.load_modules(["./submodules/qc"])

# After loading, the module is available by name
qc.run_qc(...)
```

The module's Python files are imported into `sys.modules` and bound to the **caller's globals**, so you can call them by name immediately after the `load_modules()` call.

---

### Loading from a Git repository

If the path doesn't exist locally, `load_modules()` clones it from Git. Append `@ref` to pin a version:

```python
# Clone from GitHub, default branch
jawm.utils.load_modules(["jawm_bwa"])

# Clone at a specific tag
jawm.utils.load_modules(["jawm_bwa@v1.2.0"])

# Clone at a specific branch
jawm.utils.load_modules(["jawm_bwa@develop"])

# Clone at a specific commit
jawm.utils.load_modules(["jawm_bwa@f5b27c5"])

# Use "latest" to auto-detect the highest semver tag
jawm.utils.load_modules(["jawm_bwa@latest"])
```

Cloning tries HTTPS first and falls back to SSH (non-interactive — never prompts for credentials).

---

### Loading multiple modules

Pass a list. Each entry is resolved independently:

```python
jawm.utils.load_modules([
    "jawm_bwa@v1.2.0",
    "jawm_fastqc@latest",
    "./local_tools/custom_qc",
])
```

You can mix remote repositories and local paths in the same call.

---

### Where modules are stored

When cloning, `load_modules()` places repositories in a **modules root** directory. The resolution order is:

1. **Explicit argument**: `jawm.utils.load_modules([...], modules_root="./my_modules")`
2. **Environment variable**: `JAWM_MODULES_PATH` (see [JAWM Variable Config](../config/config.md))
3. **Default**: `.submodules/` next to the calling Python file

Relative paths for `modules_root` and `JAWM_MODULES_PATH` are resolved relative to the **caller's file**, not the current working directory.

```bash
# Set a shared location for all cloned modules
export JAWM_MODULES_PATH=~/.jawm/modules
```

If the repository already exists at the destination, `load_modules()` will fetch updates from the remote and check out the requested ref — it won't re-clone from scratch.

---

### Custom Git host

By default, `load_modules()` assumes `github.com` and `mpg-age-bioinformatics`. Override with the `address` and `user` parameters:

```python
jawm.utils.load_modules(
    ["my_pipeline@v3.0"],
    address="gitlab.example.com",
    user="my-team",
)
```

---

### Idempotent imports

`load_modules()` checks `sys.modules` before importing. If a module with the same name is already loaded, it skips both the clone and the import. This means calling `load_modules()` multiple times with the same module name is safe and fast.

---

### Error handling

By default (`strict=True`), `load_modules()` exits with code 1 on the first import failure — after logging the full traceback. Set `strict=False` to log failures and continue importing whatever can be imported:

```python
jawm.utils.load_modules(["mod_a", "mod_b", "mod_c"], strict=False)
# If mod_b fails to import, mod_a and mod_c are still loaded
```

---

### Composing multiple modules

The most powerful pattern is a **parent workflow** that loads several modules and orchestrates them into a single pipeline.

#### The parent workflow pattern

```python
# pipeline.py — a parent workflow that composes three modules
import jawm

jawm.utils.load_modules([
    "jawm_sra@v2.0",
    "jawm_fastqc@latest",
    "jawm_bwa@v1.2.0",
])

# The imported modules are now in the caller's namespace.
# Each module has its own parse_arguments() and workflow() logic internally.

# Start the SRA download
sra_procs = jawm_sra.download(samples=["SRR12345", "SRR67890"])

# Run QC on the downloaded files
jawm_fastqc.run_qc(input_dir="data/raw/")

# Align to a reference genome
jawm_bwa.align(genome="hg38")

jawm.Process.wait("all")
```

_**Note**_: The exact API of each loaded module (e.g. `jawm_sra.download(...)`) depends on how that module is written. `load_modules()` just imports the Python file(s) — the module author decides what functions or classes to expose.

#### Running composed workflows with the `jawm` CLI

You can run a parent workflow through the `jawm` CLI. This gives you the full benefit of CLI logging, parameter injection, and post-run hashing — applied to the entire composed pipeline:

```bash
jawm pipeline.py -p params.yaml --global.manager=slurm
```

#### Passing variables to loaded modules

There are several ways to pass configuration into loaded modules:

**Via the `-p` / `-v` CLI flags** — variables and parameters from these files are available to all Processes created by any module in the run:

```bash
jawm pipeline.py -p global_params.yaml -v shared_vars.rc
```

**Via `--global.var.*` overrides** — these are propagated to every Process, including those created inside loaded modules:

```bash
jawm pipeline.py --global.var.GENOME=hg38 --global.var.THREADS=16
```

**Via Python** — set `var` directly on the Process or pass it through the module's own API:

```python
jawm_bwa.align(genome="hg38")  # module handles it internally
```

---

### See Also

- [Module Overview](overview.md) — what a module is and the mental model behind it.
- [Run a Module](run.md) — running modules standalone from the command line.
- [Develop a Module](develop.md) — writing your own module from scratch.
- [Utils → `load_modules()`](../utils.md#load_modules) — full function reference.
- [JAWM Variable Config](../config/config.md) — `JAWM_MODULES_PATH` and other environment variables.
