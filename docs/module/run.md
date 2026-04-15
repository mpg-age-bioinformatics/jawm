# Run a Module

This page covers how to run a jawm module — locally or from a remote Git repository — using the `jawm` CLI or directly with Python.

---

### Running a module with the `jawm` command

The `jawm` CLI is the simplest way to run a module. It handles parameter injection, logging, post-run hashing, process waiting, and cleanup automatically.

#### Local file

Point `jawm` at a Python file:

```bash
jawm my_module.py
```

#### Local directory

Point `jawm` at a directory. It will look for an entry point in this order:

1. `jawm.py` inside the directory
2. `main.py` inside the directory
3. The single `.py` file, if there is exactly one

```bash
jawm my_module/
```

#### Running directly with Python

You can also run a module as a regular Python script. This skips the `jawm` CLI wrapper — you won't get automatic process waiting, post-run hashing, or CLI logging, but it works in situations where you don't have `jawm` on `PATH` or you want full control:

```bash
python my_module.py
```

---

### Running remote modules

One of jawm's key features is that **you don't need to manually clone a module repository before running it**. The `jawm` CLI can fetch a module from Git on the fly.

#### By name

If the module doesn't exist as a local file or directory, jawm synthesizes a Git target using the default server (`github.com`) and user (`mpg-age-bioinformatics`), then clones it:

```bash
# Fetches git@github.com:mpg-age-bioinformatics/jawm_git_test.git
jawm jawm_git_test
```

The repository is cloned into the current working directory as `jawm_git_test/`, then executed.

#### Pinning to a ref

Append `@ref` to pin to a specific tag, branch, or commit:

```bash
# Specific tag
jawm jawm_git_test@v1.0.0

# Branch
jawm jawm_git_test@develop

# Commit SHA (full or abbreviated)
jawm jawm_git_test@e0490bb
```

**Special ref tokens:**

| Token | Meaning |
|---|---|
| `@latest-tag` | The tag with the highest version number (semantic comparison). |
| `@last-tag` | The most recently created tag (by date). |

```bash
jawm jawm_git_test@latest-tag
```

#### Full Git URLs

The `jawm` CLI accepts a variety of Git URL formats:

```bash
# SSH (default when synthesized)
jawm git@github.com:mpg-age-bioinformatics/jawm_git_test.git

# HTTPS
jawm https://github.com/mpg-age-bioinformatics/jawm_git_test.git

# GitHub shorthand
jawm gh:mpg-age-bioinformatics/jawm_git_test

# With a ref
jawm git@github.com:mpg-age-bioinformatics/jawm_git_test.git@v1.0.0
```

#### Subpaths inside a repository

If a repository contains multiple modules in subdirectories, use `//` to target a specific path inside the repo:

```bash
# Run the 'alignment' subdirectory inside the repo
jawm jawm_git_test@main//examples/demo.py
```

The `//` separates the repo identifier from the path within the cloned repository. This works with any of the URL formats above.

#### Custom server and user

Use `--server` and `--user` to target a different Git host or organization:

```bash
jawm my_module --server gitlab.example.com --user my-team
```

To disable remote lookup entirely (local-only mode):

```bash
jawm my_module --no-web
```

---

### CLI flags

When using the `jawm` command, these flags are available on top of whatever the module itself accepts via `parse_arguments()`:

#### Parameters and variables

| Flag | Description |
|---|---|
| `-p`, `--parameters` | One or more YAML parameter files, or a directory of them. Applied as the default `param_file` for all Processes in the module. |
| `-v`, `--variables` | One or more YAML/`.rc` variable files. Variables are injected into the module's script namespace. |

```bash
jawm my_module.py -p params.yaml vars/slurm.yaml -v secrets.rc
```

Both `-p` and `-v` accept multiple files. When multiple files are given, later files override earlier ones for overlapping keys. See [YAML Config](../config/yaml.md) for the full YAML format, and [JAWM Variable Config](../config/config.md) for environment variable options.

#### Execution control

| Flag | Description |
|---|---|
| `-l`, `--logs-directory` | Directory to store logs. CLI logs go to `<dir>/jawm_runs/`. Default: `./logs`. |
| `-r`, `--resume` | Resume mode: skip processes that already completed successfully in a previous run. |
| `-n`, `--no-override` | Disable parameter overrides. Use without a value to disable all overrides, or pass a comma-separated list of parameter names to protect selectively. |
| `-w`, `--workdir` | Change the working directory before running (creates it if missing). |
| `--stats` | Record per-process resource statistics (average/peak CPU and memory). |

```bash
jawm my_module.py -p params.yaml -l logs -r
```

#### Parameter overrides from the CLI

You can override any global or process-specific parameter directly from the command line, without editing a YAML file:

```bash
# Override a global parameter
jawm my_module.py --global.manager=slurm

# Override a global var
jawm my_module.py --global.var.GENOME=hg38

# Override a parameter for a specific process
jawm my_module.py --process.align.retries=3
```

The general syntax is:

- `--global.<key>=<value>` — applies to all processes (same as a `scope: global` entry in YAML).
- `--global.<key>.<subkey>=<value>` — for nested parameters like `var`, `env`, `manager_slurm`, etc.
- `--process.<name>.<key>=<value>` — applies only to the process with that name.

CLI overrides take the highest precedence — they override YAML files, Python arguments, and environment variables.

#### Git-related flags

| Flag | Description |
|---|---|
| `--server` | Git server host. Default: `github.com`. |
| `--user` | Git organization or username. Default: `mpg-age-bioinformatics`. |
| `--git-cache` | Path for jawm's git cache directory. Default: `~/.jawm/git`. |
| `--no-web` | Disable remote Git lookup entirely — only run local modules. |

#### Other flags

| Flag | Description |
|---|---|
| `-V`, `--version` | Print the jawm version and exit. |

---

### What happens when `jawm` runs a module

Behind the scenes, when you run `jawm my_module.py`, the CLI performs these steps:

1. **Parse CLI arguments** — `-p`, `-v`, `-l`, `-r`, `-n`, `--global.*`, `--process.*.*`, etc.
2. **Resolve the module path** — if the argument is a local file or directory, use it directly. If not found locally, attempt a remote Git lookup (unless `--no-web` is set).
3. **Clone/cache remote modules** — if the module is a Git target, clone it into the git cache (`~/.jawm/git`), then copy it to the current working directory.
4. **Set up logging** — create a CLI log file at `<logs_directory>/jawm_runs/<module>_<timestamp>.log`.
5. **Inject variables** — load any `-v` files and inject them into the module's execution namespace.
6. **Apply parameter defaults** — set `-p` files as the default `param_file`, apply `-r` (resume), `-l` (logs), and CLI overrides.
7. **Execute the module** — run the Python file via `runpy.run_path()`.
8. **Wait for all Processes** — after the module script completes, `jawm` calls `Process.wait("all")` to wait for any remaining background Processes.
9. **Post-run operations** — compute input hashes, write run history, log final status, and exit with the appropriate exit code.

---

### See Also

- [Module Overview](overview.md) — what a module is and the mental model behind it.
- [Load Modules in Workflow](load.md) — composing multiple modules in a Python workflow using `jawm.utils.load_modules()`.
- [Develop a Module](develop.md) — writing your own module from scratch.
- [Utils](../utils.md) — reference for `parse_arguments()`, `workflow()`, and other utility functions.
- [YAML Config](../config/yaml.md) — the YAML file format used with `-p`.
- [JAWM Variable Config](../config/config.md) — environment variables including `JAWM_MODULES_PATH`.
