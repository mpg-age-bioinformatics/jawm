# Utils

The `jawm.utils` module provides a collection of helper functions that make it easier to build, run, and inspect workflows. These utilities cover common workflow patterns such as batching files into processes, converting scripts to YAML, checking environment readiness, hashing content, parsing CLI arguments, loading remote modules, and pre-pulling container images.

All utilities are accessible via the fully-qualified path:

```python
import jawm
jawm.utils.<method_name>(...)
```

The utilities are organized below by purpose for easier discovery.

---

## Batch Processing

### `batch_process_file()`

Create — and optionally execute — one [`Process`](process/overview.md) per file in a directory. This is useful when the same workflow step needs to be applied to many input files (e.g., one alignment job per FASTQ).

- **Signature:** `jawm.utils.batch_process_file(directory, process_template=None, include="*", exclude=None, recursive=False, execute=True, filename_prefix="batch_", filename_identifier="filename")`
- **Returns:** `list[Process]` — the list of created `Process` instances.

**Parameters**

| Parameter | Description |
|---|---|
| `directory` | Folder to scan for input files. |
| `process_template` | A dict of `Process` parameters used as the template for every generated process (e.g. `{"script": "process.py", "manager": "local"}`). |
| `include` | Glob pattern (or list of patterns) to include files. Default: `"*"` (all files). |
| `exclude` | Glob pattern (or list of patterns) to exclude files. |
| `recursive` | If `True`, scan subdirectories. Default: `False`. |
| `execute` | If `True`, immediately calls `.execute()` on every generated process. Default: `True`. |
| `filename_prefix` | Prefix prepended to each generated process name. Default: `"batch_"`. |
| `filename_identifier` | Naming strategy: `"filename"` (file basename), `"index"` (numeric), or `"filename_index"` (both). |

For each file, jawm injects the absolute path as the variable `INPUT_FILE` so the script can read it directly.

**Example**

```python
import jawm

procs = jawm.utils.batch_process_file(
    directory="data/fastq",
    include="*.fastq.gz",
    process_template={
        "script": "scripts/qc.py",
        "manager": "local",
        "logs_directory": "logs",
    },
    execute=True,
)
```

---

## Script ↔ YAML Conversion

### `script_to_yaml()`

Convert a Python, R, or shell script into a jawm parameter YAML entry. Handy when you want a self-contained YAML file that embeds the script body — useful for sharing or for workflows where Python is just `p = jawm.Process(name="...")`.

- **Signature:** `jawm.utils.script_to_yaml(script_path=None, *, script_text=None, name=None, output_file=None, inline=True, shebang=True, language=None, scope="process", **kwargs)`
- **Returns:** YAML string (or output path, if `output_file` is set).

**Parameters**

| Parameter | Description |
|---|---|
| `script_path` | Path to a script file (`.py`, `.R`, `.sh`, `.bash`, `.zsh`, …). |
| `script_text` | Raw script content (use this when no file exists). |
| `name` | Process name. Defaults to the file's basename without extension. |
| `output_file` | If set, the YAML is written to this path and the path is returned. |
| `inline` | If `True` (default), embed the script under `script: \|`. If `False`, reference it as `script_file: <path>`. |
| `shebang` | `True` (auto-infer), a custom shebang string, or `False` to leave the script untouched. |
| `language` | Hint to infer the shebang when the extension is ambiguous (e.g., `"python"`, `"r"`, `"bash"`). |
| `scope` | YAML scope for the entry. Default: `"process"`. |
| `**kwargs` | Any other Process parameters (e.g. `manager="local"`, `logs_directory="logs"`). |

_**Note**_: The keys `script` and `script_file` are reserved and cannot be passed via `**kwargs`.

**Example**

```python
import jawm

# Embed a Python script inline into a YAML file
jawm.utils.script_to_yaml(
    "scripts/hello.py",
    output_file="params/hello.yaml",
    manager="local",
)

# Generate YAML from raw text
yaml_text = jawm.utils.script_to_yaml(
    script_text="print('hi')\n",
    name="hello_py",
    language="python",
)
```

---

## Environment Detection

These checks let your workflow adapt to whatever container or scheduler is available — for example, by switching backends or skipping unsupported steps.

### `docker_available()`

Check whether Docker is installed and the daemon is reachable.

- **Signature:** `jawm.utils.docker_available(v=False)`
- **Returns:** `bool` — `True` if `docker info` succeeds within 3 seconds.

```python
if jawm.utils.docker_available():
    p = jawm.Process(name="job", environment="docker", container="python:3.11-slim")
```

---

### `apptainer_available()`

Check whether Apptainer (formerly Singularity) is installed.

- **Signature:** `jawm.utils.apptainer_available(v=False)`
- **Returns:** `bool` — `True` if `apptainer --version` succeeds within 3 seconds.

```python
if jawm.utils.apptainer_available(v=True):
    print("Apptainer is ready.")
```

---

### `kubernetes_available()`

Check whether `kubectl` is installed and a cluster is reachable.

- **Signature:** `jawm.utils.kubernetes_available(v=False)`
- **Returns:** `bool` — `True` if `kubectl cluster-info` succeeds within 3 seconds.

```python
if not jawm.utils.kubernetes_available(v=True):
    raise RuntimeError("Kubernetes cluster is not reachable.")
```

In all three checks, set `v=True` to log diagnostic messages explaining why the check failed.

---

## Container Images

### `get_image()`

Pre-pull container images so that Docker or Apptainer won't pull them implicitly during workflow execution. Pre-pulling is especially useful in HPC and CI environments where parallel runs would otherwise fight over the same image cache.

- **Signature:** `jawm.utils.get_image(image=None, mode="auto", v=True)`
- **Returns:** `dict` — mapping of image to `{"ok": bool, "method": str, "error": str?}`.

**Parameters**

| Parameter | Description |
|---|---|
| `image` | A single image string, a list of image strings, or `None`. If `None`, jawm pulls every container referenced by the **registered, not-yet-executed** processes in `Process.registry`. |
| `mode` | `"auto"` (prefer Docker, fall back to Apptainer), `"docker"`, `"apptainer"` (alias: `"singularity"`), or `"all"` (try every available engine). |
| `v` | If `True` (default), log progress messages. |

**Example**

```python
import jawm

# Define processes first…
jawm.Process(name="step1", container="python:3.11-slim", environment="docker")
jawm.Process(name="step2", container="alpine:3.20", environment="docker")

# …then pre-pull every image they reference.
results = jawm.utils.get_image()
```

---

## Hashing

### `write_hash_file()`

Compute a hash of the content of one or more files/folders and write it to a file. If the file already exists, its stored hash is compared against the freshly computed one — making this a simple way to detect changes in inputs, references, or pipelines.

- **Signature:** `jawm.utils.write_hash_file(paths, hash_file, hash_func=hashlib.sha256, v=True, exclude_dirs=None, exclude_files=None, allowed_extensions=None, recursive=True, consider_name=False)`
- **Returns:** `bool` — `True` if the hash was written or matched the existing one; `False` if the existing hash differs.

**Parameters**

| Parameter | Description |
|---|---|
| `paths` | A path or list of paths (files and/or folders) to hash. |
| `hash_file` | File where the hash will be stored or read from. |
| `hash_func` | Any callable from `hashlib` (default: `hashlib.sha256`). |
| `exclude_dirs` | Directory name patterns to skip (uses `fnmatch`). |
| `exclude_files` | File name patterns to skip. |
| `allowed_extensions` | Restrict hashing to files with these extensions when scanning a directory. |
| `recursive` | Recurse into subdirectories. Default: `True`. |
| `consider_name` | Also include filenames (not only contents) in the hash. |

```python
import jawm

ok = jawm.utils.write_hash_file(
    paths=["scripts/", "config.yaml"],
    hash_file="run.hash",
    allowed_extensions=[".py", ".yaml"],
)
if not ok:
    print("Inputs changed since last run!")
```

---

### `hash_content()`

Compute a combined hash digest for files and/or folders, **without** writing it to disk. This is the lower-level primitive that `write_hash_file()` uses internally.

- **Signature:** `jawm.utils.hash_content(paths, hash_func=hashlib.sha256, exclude_dirs=None, exclude_files=None, allowed_extensions=None, recursive=True, consider_name=False)`
- **Returns:** `str` — the hex digest.

```python
digest = jawm.utils.hash_content(["scripts/", "config.yaml"])
print(digest)
```

The arguments mirror `write_hash_file()` exactly (minus `hash_file` and `v`).

---

## Variables

### `read_variables()`

Load `var` definitions from one or more YAML files, `.rc` files, or a directory containing such files. Optionally inject the resulting variables directly into a Python namespace so the script can use them as bare names.

- **Signature:** `jawm.utils.read_variables(file_or_list_or_dir, process_name=None, output_type="var", namespace=None)`
- **Returns:** `dict` — the merged variable mapping (always returned).

**Parameters**

| Parameter | Description |
|---|---|
| `file_or_list_or_dir` | A YAML/`.rc` file, a list of files, or a directory containing YAML files. |
| `process_name` | If set, also include process-scoped `var` blocks whose `name` matches (wildcards supported). |
| `output_type` | `"var"` injects each key as a Python variable; `"dict"` only returns the dict. |
| `namespace` | Namespace to inject into when `output_type="var"`. Defaults to the caller's globals. |

```python
import jawm

# Read both a YAML and a .rc file, inject variables into globals
jawm.utils.read_variables(["params.yaml", "secrets.rc"])

# Or just get them as a dict
cfg = jawm.utils.read_variables("params.yaml", output_type="dict")
```

For YAML files, both `global`-scoped and matching `process`-scoped `var` blocks are merged. See the [YAML Config](config/yaml.md) page for the full file format.

---

## Files & Inputs

### `from_file_pairs()`

Mimics Nextflow's `Channel.fromFilePairs` for paired-end FASTQ files. Returns a dict mapping each sample name to a list of `[read_1, read_2]` paths, suitable for feeding directly into a batch of processes.

- **Signature:** `jawm.utils.from_file_pairs(data_folder, read1_suffix=".READ_1.fastq.gz", read2_suffix=".READ_2.fastq.gz")`
- **Returns:** `dict[str, list[str]]` — `{sample_name: [read1_path, read2_path]}`.

```python
pairs = jawm.utils.from_file_pairs(
    "data/raw",
    read1_suffix="_R1.fastq.gz",
    read2_suffix="_R2.fastq.gz",
)

for sample, (r1, r2) in pairs.items():
    jawm.Process(
        name=f"align_{sample}",
        script="scripts/align.sh",
        var={"R1": r1, "R2": r2, "SAMPLE": sample},
    )
```

---

### `id_files()`

Recursively scan a directory for files of a given extension and group them under unique, human-friendly IDs. Useful for collecting samples that may share common basenames but live in different directories — or for grouping paired files by varying parts (e.g. `Read_1`/`Read_2`).

- **Signature:** `jawm.utils.id_files(root=".", ext=".bam", varying_parts=None)`
- **Returns:** `dict[str, list[str]]` — `{id: [file_paths]}`.

**Parameters**

| Parameter | Description |
|---|---|
| `root` | Directory to scan (default: current directory). |
| `ext` | File extension to match (e.g. `".bam"`, `".fastq.gz"`). A leading dot is added if missing. |
| `varying_parts` | Substrings that vary between files within the same logical sample (ordering controls how matched files are sorted in the output). |

**ID selection rules** (per group, in order):

1. The nearest unique parent directory name across all groups.
2. Otherwise, the common basename (basename minus `varying_parts` and extension), if it is unique.
3. Otherwise, a fallback `"<parent>-<common_basename>"`.

```python
# Group paired-end FASTQ files
samples = jawm.utils.id_files(
    root="data/fastq",
    ext=".fastq.gz",
    varying_parts=["Read_1", "Read_2"],
)
# {"sample_A": ["sample_A.Read_1.fastq.gz", "sample_A.Read_2.fastq.gz"], …}
```

---

## Module Loading

### `load_modules()`

Dynamically import Python modules or whole repositories — including remote ones from a Git host. This is the mechanism behind jawm's reusable [modules](module.md): a workflow can import shared code from a Git repository without manually cloning it.

- **Signature:** `jawm.utils.load_modules(paths, *, address="github.com", user="mpg-age-bioinformatics", modules_root=None, strict=True)`
- **Returns:** `list[str]` — the names of successfully imported modules.

**Parameters**

| Parameter | Description |
|---|---|
| `paths` | A path or list of paths/specs. A spec may be `"repo"` or `"repo@ref"` (where `ref` is a branch, tag, commit, or `"latest"`). |
| `address` | Git host. Default: `github.com`. |
| `user` | Default organization or user on the Git host. |
| `modules_root` | Where to clone or look for modules. Resolution order: explicit argument → `JAWM_MODULES_PATH` env var → `<caller_dir>/.submodules`. |
| `strict` | If `True` (default), exit on the first import failure (after logging the traceback). If `False`, log and continue. |

**Behavior**

- Relative paths and the modules root are resolved relative to the **caller's file**, not the current working directory or jawm's installation directory.
- Repositories already present are reused; jawm will fetch updates and check out the requested ref.
- Cloning tries HTTPS first and falls back to SSH (non-interactive — never prompts).
- Modules already in `sys.modules` are skipped, so calling `load_modules()` repeatedly is safe.
- Imported modules are also bound into the **caller's globals**, so you can call them by name immediately after.

```python
import jawm

# Pull a specific tag of a shared workflow library
jawm.utils.load_modules(["workflow_modules@v1.2.0"])

# After loading, the module is available by name in the caller's namespace
workflow_modules.run_qc(...)
```

---

## CLI Helpers

### `parse_arguments()`

Parse command-line arguments for jawm-style workflow scripts. This is the standard entry point used by workflow modules to determine which sub-workflows to run, and to load parameter and variable files passed on the CLI.

- **Signature:** `jawm.utils.parse_arguments(available_workflows=["main"], description="A jawm module.", extra_args={})`
- **Returns:** `tuple` — `(workflows, var, args, unknown_args)`
    - `workflows`: list of selected workflow names.
    - `var`: merged dict of variables (from `-p`/`-v`, sanitized).
    - `args`: parsed `argparse.Namespace`.
    - `unknown_args`: any extra positional/keyword args that argparse did not consume.

**Parameters**

| Parameter | Description |
|---|---|
| `available_workflows` | List of valid sub-workflow names. Anything outside this list causes the program to exit with an error. |
| `description` | Description shown by `--help`. |
| `extra_args` | Dict of `{flag: help_text}` for additional argparse arguments. |

**Built-in CLI flags**

| Flag | Purpose |
|---|---|
| `workflows` (positional) | Workflow name(s). Use `main` to run all, or a comma-separated list. |
| `-p`, `--parameters` | YAML file(s) or directory of parameter configs. |
| `-v`, `--variables` | YAML/`.rc` file(s) or directory of script variables. |
| `-l`, `--logs_directory` | Default logs directory. |
| `-r`, `--resume` | Skip already-completed processes on rerun. |
| `-n`, `--no_override` | Disable override for all or specific parameters. |
| `--git-cache` | Path for jawm's git cache. |

```python
# my_workflow.py
import jawm

workflows, var, args, _ = jawm.utils.parse_arguments(
    available_workflows=["main", "qc", "align"],
    description="My sequencing pipeline.",
)

if "qc" in workflows:
    ...
```

```bash
python my_workflow.py qc,align -p params.yaml -v vars.rc
```

---

### `workflow()`

Filter a list of workflow names against a selection. A small but commonly used helper inside jawm modules to decide which sub-workflows should run for the current invocation.

- **Signature:** `jawm.utils.workflow(select=None, workflows=None)`
- **Returns:** `list` — workflows present in both `workflows` and `select` (preserving the order of `workflows`).

```python
selected = jawm.utils.workflow(select=["qc", "align"], workflows=["qc", "align", "report"])
# ['qc', 'align']
```

If `select` is a string, it is treated as a single-element list. Both default to an empty list when `None`, so this function is safe to call without arguments.

---

## See Also

- [Process Overview](process/overview.md) — the core abstraction these utilities operate on.
- [YAML Config](config/yaml.md) — the file format consumed by `read_variables()` and `script_to_yaml()`.
- [JAWM Variable Config](config/config.md) — environment variables such as `JAWM_MODULES_PATH` used by `load_modules()`.
- [Module](module.md) — building reusable workflow modules with `load_modules()` and `parse_arguments()`.
