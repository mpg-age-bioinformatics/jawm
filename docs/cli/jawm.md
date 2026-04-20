# jawm

`jawm` is the primary command-line entry point for running workflow modules. It resolves the module (locally or from a remote Git repository), injects parameters and variables, executes the workflow, and performs post-run hashing and logging — all in one step.

```bash
jawm <module> [workflow] [flags]
```

---

### Synopsis

```
jawm <module> [workflow] [-p YAML...] [-v FILE...] [-l DIR] [-w DIR]
     [-r] [-n [KEYS]] [--server HOST] [--user ORG] [--no-web]
     [--git-cache DIR] [--stats] [-V]
     [--global.<key>=<value> ...]
     [--process.<name>.<key>=<value> ...]
```

---

### Flags

#### Core

| Flag | Default | Description |
|------|---------|-------------|
| `-p`, `--parameters` | — | YAML file(s) or directory of parameter configs. Sets `param_file` on all Processes. Can be repeated or space-separated. |
| `-v`, `--variables` | — | YAML or `.rc` file(s) of script variables. Merged into each Process's `var`. Can be repeated or space-separated. |
| `-l`, `--logs-directory` | `./logs` | Base directory for log files. CLI run logs are written to `<dir>/jawm_runs/`. |
| `-w`, `--workdir` | — | Change working directory before resolving any paths. Created automatically if it does not exist. |
| `-r`, `--resume` | `False` | Resume mode — skip any Process that already completed successfully in a previous run. |
| `-n`, `--no-override` | — | Disable parameter overrides. Use alone (`-n`) to lock all parameters, or pass a comma-separated list of keys to lock specific ones (`-n manager,env`). |
| `--stats` | `False` | Record per-process CPU and memory usage (average and peak). |
| `-V`, `--version` | — | Print the installed jawm version and exit. |

#### Git / remote

| Flag | Default | Description |
|------|---------|-------------|
| `--server` | `github.com` | Git server host used when resolving module names to SSH URLs. |
| `--user` | `mpg-age-bioinformatics` | Git user or organisation used when resolving bare module names. |
| `--no-web` | `False` | Disable online module lookup. jawm will only resolve modules that exist locally. |
| `--git-cache` | `~/.jawm/git` | Local directory used as the Git clone cache. |

#### `-p` / `--parameters`

Passes one or more YAML files (or a directory of YAMLs) as `param_file` to every Process in the module. These files set Process configuration — manager, environment, container, retries, and so on.

```bash
jawm mymodule.py -p params.yaml
jawm mymodule.py -p params/base.yaml params/slurm.yaml
jawm mymodule.py -p params/          # all YAMLs in the directory
```

HTTPS URLs are also accepted — jawm downloads and caches the file before the run:

```bash
jawm mymodule.py -p https://example.com/configs/hg38.yaml
```

#### `-v` / `--variables`

Passes one or more YAML or `.rc` files as variable sources. The key-value pairs in these files are substituted into `{{placeholder}}` tokens in each Process's script. Multiple files are merged in order.

```bash
jawm mymodule.py -v vars.yaml
jawm mymodule.py -v samples.yaml paths.yaml
```

`-p` and `-v` can be used together — parameters control how Processes run, variables control what they run with:

```bash
jawm mymodule.py -p slurm.yaml -v sample_vars.yaml
```

#### `-l` / `--logs-directory`

Sets the base directory for all log output. Each Process writes its stdout, stderr, script, and exit code into a subdirectory here. The CLI run log (a full transcript of the terminal output) is written to `<logs directory>/jawm_runs/`.

```bash
jawm mymodule.py -l /scratch/project/logs
```

Defaults to `./logs` in the current working directory.

#### `-w` / `--workdir`

Changes the working directory before jawm resolves any paths or runs the module. Useful when you want all relative paths in your module and YAML files to resolve against a specific project directory.

```bash
jawm mymodule.py -w /scratch/project123 -p params.yaml
```

The directory is created automatically if it does not exist.

#### `-r` / `--resume`

Enables resume mode. jawm checks each Process against its previous run logs — if a Process already completed successfully (exit code `0`), it is skipped and its previous logs and outputs are reused. Only Processes that failed or were not yet run are executed.

```bash
jawm mymodule.py -v vars.yaml -r
```

Resume is particularly useful for long pipelines where you want to pick up after a partial failure without re-running steps that already succeeded.

#### `-n` / `--no-override`

Prevents jawm from applying override-level parameters. By default, `-p` files are applied as overrides (highest precedence). Use `-n` to make them behave as defaults instead, allowing the module's own parameter definitions to take precedence.

```bash
# Lock all parameters — module defaults win over -p files
jawm mymodule.py -p params.yaml -n

# Lock only specific keys
jawm mymodule.py -p params.yaml -n manager,env
```

#### `--server` / `--user`

Control how bare module names (like `jawm_bwa`) are resolved to Git SSH URLs. jawm constructs the URL as `git@<server>:<user>/<name>.git`.

```bash
# Default: git@github.com:mpg-age-bioinformatics/jawm_bwa.git
jawm jawm_bwa

# Custom server and org
jawm jawm_bwa --server gitlab.example.org --user my-team
# → git@gitlab.example.org:my-team/jawm_bwa.git
```

#### `--no-web`

Disables all online module resolution. When set, jawm will only run modules that exist as local files or directories — it will not attempt to clone from any Git server.

```bash
jawm ./my_pipeline/ --no-web -p params.yaml
```

Useful in air-gapped environments or when you want to ensure no network calls are made.

---

### Module argument

The `<module>` argument tells jawm what to run. It is flexible — it can be a local path, a repository name, or a full Git URL.

#### Local file or directory

```bash
# A single Python file
jawm align.py

# A directory — jawm looks for jawm.py, then main.py, then the only .py file
jawm ./my_pipeline/
jawm .    # current directory
```

When a directory is given, jawm picks the entry point in this order:

1. `jawm.py`
2. `main.py`
3. The only `.py` file (fails if more than one exists and none of the above match)

#### Remote module by name

If the module path does not exist locally and is not already a Git URL, jawm automatically constructs a Git SSH URL from `--server` and `--user`:

```bash
# Resolves to git@github.com:mpg-age-bioinformatics/jawm_bwa.git
jawm jawm_bwa

# With an explicit org prefix
jawm mpg-age-bioinformatics/jawm_bwa
```

Use `--no-web` to disable this behaviour and only resolve modules locally.

#### Full Git URL

Any valid Git SSH or HTTPS URL is accepted directly:

```bash
jawm git@github.com:org/jawm_rnaseq.git
jawm https://github.com/org/jawm_rnaseq.git
```

#### Pinning to a ref with `@`

Append `@<ref>` to any module name or Git URL to pin to a specific branch, tag, or commit:

```bash
jawm jawm_bwa@v1.2.0          # tag
jawm jawm_bwa@main            # branch
jawm jawm_bwa@4f3a2c1         # commit SHA

# Two special tokens resolve automatically:
jawm jawm_bwa@latest-tag      # highest semantic version tag
jawm jawm_bwa@last-tag        # most recently created tag
```

`@latest-tag` picks the tag that sorts highest numerically (e.g. `v2.1.0` beats `v1.9.0`). `@last-tag` picks the tag most recently created by creation timestamp, regardless of version number.

#### Subpath with `//`

Run a module nested inside a repository:

```bash
jawm jawm_rnaseq//submodules/qc
jawm git@github.com:org/jawm_rnaseq.git//submodules/qc
```

Everything after `//` is treated as a path relative to the repository root.

---

### Parameter overrides

Two special flag namespaces let you override any Process parameter directly from the command line, at the highest precedence level — they override YAML files, module defaults, and everything else.

#### `--global.<key>=<value>`

Applies an override to **all** Processes in the module:

```bash
# Set manager to slurm for every process
jawm mymodule.py --global.manager=slurm

# Set a script variable for all processes
jawm mymodule.py --global.var.threads=16

# Set an environment variable for all processes
jawm mymodule.py --global.env.TMPDIR=/scratch/tmp
```

#### `--process.<name>.<key>=<value>`

Applies an override to a **single named Process**:

```bash
# Increase retries for one process
jawm mymodule.py --process.bwa_align.retries=3

# Override a variable for one process only
jawm mymodule.py --process.bwa_align.var.genome=/data/ref/hg38.fa

# Change manager for one process
jawm mymodule.py --process.sort_bam.manager=local
```

Both forms accept either `=` syntax or space-separated syntax:

```bash
jawm mymodule.py --global.var.threads=16
jawm mymodule.py --global.var.threads 16   # equivalent
```

Multiple overrides can be combined freely:

```bash
jawm mymodule.py \
  --global.manager=slurm \
  --global.var.threads=16 \
  --process.bwa_align.var.genome=/data/ref/hg38.fa \
  --process.bwa_align.retries=3
```

---

### Remote parameter files

`-p` and `-v` accept HTTPS URLs in addition to local paths. jawm downloads and caches the file before the run:

```bash
jawm mymodule.py -p https://example.com/params/hg38.yaml
```

Downloaded files are cached in `~/.jawm/remote_params/` (override with `JAWM_URL_CACHE_DIR`). jawm will reuse the cached copy on subsequent runs unless `JAWM_URL_FORCE_REFRESH=1` is set.

---

### What jawm does when you run it

When you invoke `jawm mymodule.py -p params.yaml`, the following happens in order:

1. **Parse arguments** — flags, workflow name, override tokens, and the `//subpath` suffix are extracted
2. **Resolve the module** — if the module is not a local path, jawm builds a Git SSH URL and clones it into the current directory. If a matching local folder already exists with the same commit, it is reused without cloning again
3. **Apply `--workdir`** — if set, jawm changes the working directory before any paths are resolved
4. **Set up logging** — a timestamped CLI log file is created at `<logs>/jawm_runs/<module>_<timestamp>.log`. Everything printed to the terminal is also written to this file
5. **Apply parameters and variables** — `-p` sets `param_file` on all Processes; `-v` sets `var_file` and injects variables into the script execution namespace; `--resume` and `--logs-directory` are applied as Process-level overrides
6. **Parse and store `--global.*` / `--process.*.*` overrides** — stored on the Process class for consumption by each Process at initialisation time
7. **Execute the module** — the Python file is run with `runpy.run_path()`. Processes defined inside it call `.execute()` which spawns background threads
8. **Wait for all Processes** — after the module file finishes, jawm automatically waits for every registered Process to complete (up to 24 hours, configurable via `JAWM_WAIT_TIMEOUT`)
9. **Post-run hashing** — output hashes are computed and written to `<logs>/jawm_hashes/<module>.hash`. These are the hashes that `jawm-test` compares against stored references
10. **Exit** — jawm exits with the module's exit code, or `0` if the module did not call `sys.exit()`

---

### Logs

Every `jawm` run writes two kinds of logs:

- **CLI run log** — `<logs>/jawm_runs/<module>_<timestamp>.log` — a full transcript of everything printed to the terminal during the run, including all Process-level log lines
- **Per-process logs** — `<logs>/<process_name>/` — individual stdout, stderr, script, and exit code files for each Process

The base logs directory defaults to `./logs` and can be changed with `-l`.

---

### Environment variables

These environment variables affect `jawm` behaviour without needing a command-line flag:

| Variable | Default | Description |
|----------|---------|-------------|
| `JAWM_GIT_CACHE` | `~/.jawm/git` | Override the Git clone cache directory. Use `.` to place it in `<cwd>/git`. |
| `JAWM_WAIT_TIMEOUT` | `86400` (24h) | Maximum seconds to wait for all Processes after the module finishes. |
| `JAWM_WAIT_CLI` | `1` | Set to `0` to skip the automatic post-module wait. |
| `JAWM_RECORD_STAT` | `0` | Set to `1` to enable per-process resource stats (equivalent to `--stats`). |
| `JAWM_LOG_EMOJI` | `1` | Set to `0` to strip emoji from log messages. |
| `JAWM_ALLOW_URL_CONFIG` | `1` | Set to `0` to disallow remote HTTPS parameter files passed via `-p` / `-v`. |
| `JAWM_URL_CACHE_DIR` | `~/.jawm/remote_params` | Directory for caching downloaded remote parameter files. |
| `JAWM_URL_FORCE_REFRESH` | `0` | Set to `1` to re-download remote parameter files even if a cached copy exists. |

---

### Examples

```bash
# Run a local module with a parameter file
jawm align.py -p params.yaml

# Run and override a variable inline
jawm align.py -v vars.yaml --global.var.threads=32

# Run only the 'qc' sub-workflow
jawm rnaseq.py qc -v vars.yaml

# Run from a remote Git repository, pinned to a tag
jawm jawm_bwa@v1.0.0 -v vars.yaml

# Run with Slurm for all processes, override one process back to local
jawm mymodule.py \
  --global.manager=slurm \
  --process.download.manager=local

# Resume a previously started run (skip completed processes)
jawm mymodule.py -v vars.yaml -r

# Use a custom git server and organisation
jawm jawm_align --server gitlab.example.org --user my-team

# Run without internet access (local only)
jawm ./my_pipeline/ --no-web -p params.yaml

# Change working directory before running
jawm mymodule.py -w /scratch/project123 -p params.yaml
```
