# Develop a Module

This page walks through how to write a jawm module from scratch — from the initial scaffold all the way to testing and publishing with example of ways to do that.

---

### Scaffolding a new module

The fastest way to start is with `jawm-dev init`:

```bash
jawm-dev init my_pipeline
```

This will:

1. Download the [`jawm_demo`](https://github.com/mpg-age-bioinformatics/jawm_demo) template.
2. Create a directory called `jawm_my_pipeline/` with a ready-to-run skeleton.
3. Rename the template files to match your module name (`my_pipeline.py`, submodule files, etc.).
4. Initialize a Git repository and, if possible, create a matching remote on GitHub.

**Options:**

| Flag | Description |
|---|---|
| `-s`, `--server` | Git server host. Use `local` to skip remote creation. Default: `github.com`. |
| `-u`, `--user` | Git organization or username for the remote. Default: `mpg-age-bioinformatics`. |
| `-p`, `--prefix` | Repository directory prefix. Default: `jawm_`. |

```bash
# Create a local-only module (no remote)
jawm-dev init my_pipeline -s local

# Target a different Git server
jawm-dev init my_pipeline -s gitlab.example.com -u my-team
```

Remote creation is supported for **GitHub** (via `gh` CLI or `GITHUB_TOKEN`), **GitLab** (`GITLAB_TOKEN`), and **Gitea** (`GITEA_TOKEN`). For other hosts, the repository is initialized locally and the remote URL is set — you push manually.

After scaffolding, test immediately:

```bash
cd jawm_my_pipeline
jawm my_pipeline.py -p ./yaml/docker.yaml
```

---

### The module skeleton

Whether you scaffold with `jawm-dev init` or start from an empty file, a jwam module can follow a base skeleton; but jawm is developer friendly and there is no strict protocol on the modules structure.

```python
# my_pipeline.py
import jawm

workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    ["main", "align", "qc", "test"],
    description="My sequencing pipeline.",
)

# --- align sub-workflow ---
if jawm.utils.workflow(["main", "align"], workflows):
    jawm.Process(
        name="bwa_align",
        script="scripts/align.sh",
        logs_directory="logs",
    ).execute()

# --- qc sub-workflow ---
if jawm.utils.workflow(["main", "qc"], workflows):
    jawm.Process(
        name="fastqc",
        script="scripts/fastqc.sh",
        logs_directory="logs",
    ).execute()

# --- test sub-workflow ---
if jawm.utils.workflow(["main", "test"], workflows):
    jawm.Process(
        name="pipeline_test",
        script="#!/bin/bash\necho 'pipeline module is healthy'",
        logs_directory="logs",
    ).execute()
```

There are four key pieces at work here. Let's walk through each one.

---

### `parse_arguments()` — declare your sub-workflows

The first thing a module does is call [`jawm.utils.parse_arguments()`](../utils.md#parse_arguments):

```python
workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    ["main", "align", "qc", "test"],
    description="My sequencing pipeline.",
)
```

The first argument is a list of **all valid sub-workflow names** this module knows about. If a user passes a name that isn't in this list, jawm logs the valid options and exits with code 1. The return values are:

| Return | What it contains |
|---|---|
| `workflows` | The sub-workflow names the user actually requested (defaults to `["main"]`). |
| `var` | A merged dict of variables loaded from any `-p` / `-v` files the user passed. |
| `args` | The full `argparse.Namespace` — includes `args.logs_directory`, `args.resume`, `args.no_override`, etc. |
| `unknown_args` | CLI tokens that argparse didn't recognize, so you can forward them if needed. |

#### Using `var`

The `var` dict gives your module access to variables defined in YAML parameter files or `.rc` files. You can use it to pass configuration into your Processes:

```python
workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    ["main", "align"],
)

if jawm.utils.workflow(["main", "align"], workflows):
    jawm.Process(
        name="bwa_align",
        script="scripts/align.sh",
        var={
            "GENOME": var.get("GENOME", "hg38"),
            "THREADS": var.get("THREADS", "4"),
        },
    ).execute()
```

The user can then set these from the CLI:

```bash
jawm my_pipeline.py main -v vars.yaml
```

Or with `--global.var.*` overrides:

```bash
jawm my_pipeline.py main --global.var.GENOME=mm10 --global.var.THREADS=8
```

---

### `workflow()` — gate your sub-workflows

Each block of Processes is wrapped in an `if jawm.utils.workflow(...)` gate:

```python
if jawm.utils.workflow(["main", "align"], workflows):
    # alignment processes here
    ...
```

[`jawm.utils.workflow()`](../utils.md#workflow) returns the intersection of the two lists. Since an empty list is falsy in Python, the block only runs if the user selected at least one of the names in the first argument.

**Why `"main"` appears in every gate:** by convention, `main` means "run everything this module knows how to do." Including `"main"` in each gate is what makes that convention work — it's not a keyword, just a name that each gate opts into.

**Structuring gates for control:** you can group processes under different gates to give users fine-grained control:

```python
# Runs on "main" or "align"
if jawm.utils.workflow(["main", "align"], workflows):
    jawm.Process(name="bwa_index", ...).execute()
    jawm.Process(name="bwa_align", ...).execute()

# Runs on "main" or "qc"
if jawm.utils.workflow(["main", "qc"], workflows):
    jawm.Process(name="fastqc", ...).execute()

# Runs on "main" or "test" — but NOT on "align" or "qc" alone
if jawm.utils.workflow(["main", "test"], workflows):
    jawm.Process(name="pipeline_test", ...).execute()
```

With this setup:

| Command | What runs |
|---|---|
| `python my_pipeline.py main` | Everything (align + qc + test) |
| `python my_pipeline.py align` | Only alignment |
| `python my_pipeline.py align,qc` | Alignment + QC |
| `python my_pipeline.py test` | Only the health check |

---

### Directory layout

A module is often more than a single `.py` file. Here's the conventional layout used across published jawm modules:

```
jawm_my_pipeline/
├── my_pipeline.py          # Module entry point
├── scripts/                # Shell / Python / R scripts
│   ├── align.sh
│   ├── fastqc.sh
│   └── report.py
├── submodules/             # Optional: loaded sub-modules
│   └── jawm_my_pipeline_submodule/
│       └── my_pipeline_submodule.py
├── yaml/                   # Default parameter YAMLs
│   ├── docker.yaml
│   └── slurm.yaml
├── test/                   # Test configuration
│   ├── tests.txt           # Test definitions (module;workflow;params;"name";hash)
│   └── data.txt            # Optional: test input downloads (md5 filename url)
├── .github/workflows/      # CI workflows
│   └── test.yaml
└── README.md
```

_**Note**_: Nothing in jawm enforces this layout. Your module could be a single `.py` file with inline scripts. But the layout above is what `jawm-dev init` scaffolds and what published modules follow, so it's worth sticking to for consistency.

#### Scripts directory

Scripts referenced by Processes live in `scripts/`. Each Process points to its script via the `script` parameter (for inline content) or `script_file` (for a file path):

```python
# Inline script
jawm.Process(
    name="hello",
    script="#!/bin/bash\necho hello",
)

# Script file
jawm.Process(
    name="align",
    script_file="scripts/align.sh",
)
```

#### YAML directory

The `yaml/` directory holds default parameter files. Users pass them with `-p`:

```bash
jawm my_pipeline.py main -p yaml/docker.yaml
```

A typical `yaml/docker.yaml` might look like:

```yaml
- scope: global
  manager: local
  environment: docker
  container: "python:3.11-slim"
  logs_directory: ./logs
```

See [YAML Config](../config/yaml.md) for the full YAML format.

---

### Sub-modules

For larger modules, you can split workflows across multiple Python files. The main entry point loads sub-modules using `jawm.utils.load_modules()`:

```python
# my_pipeline.py
import jawm

jawm.utils.load_modules(["./submodules/jawm_my_pipeline_submodule"])

workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    ["main", "align", "qc", "report", "test"],
    description="My pipeline with sub-modules.",
)

if jawm.utils.workflow(["main", "align"], workflows):
    jawm.Process(name="bwa_align", script="scripts/align.sh").execute()

# Delegate reporting to the sub-module
if jawm.utils.workflow(["main", "report"], workflows):
    my_pipeline_submodule.run_reports()
```

The sub-module (`my_pipeline_submodule.py`) is a regular Python file that defines functions or Process definitions. After `load_modules()` imports it, it's available by name in the caller's namespace.

See [Load Modules in Workflow](load.md) for the full details on `load_modules()`.

---

### Adding custom CLI flags

If your module needs extra CLI options beyond the built-in ones, use the `extra_args` parameter:

```python
workflows, var, args, unknown_args = jawm.utils.parse_arguments(
    ["main", "align"],
    description="Alignment module with genome selection.",
    extra_args={
        "--genome": "Reference genome build (e.g. hg38, mm10)",
        "--aligner": "Aligner to use (bwa or bowtie2)",
    },
)

# Access the custom flags from the args namespace
genome = args.genome or "hg38"
aligner = args.aligner or "bwa"

if jawm.utils.workflow(["main", "align"], workflows):
    jawm.Process(
        name="align",
        script_file=f"scripts/{aligner}_align.sh",
        var={"GENOME": genome},
    ).execute()
```

```bash
python my_pipeline.py align --genome mm10 --aligner bowtie2
```

Custom flags appear in `--help` alongside the built-in flags.

---

### Process dependencies

Within a module, you can declare dependencies between Processes so they execute in the right order. Use the `depends_on` parameter with the upstream Process's hash or name:

```python
p1 = jawm.Process(name="download", script="scripts/download.sh")
p1.execute()

p2 = jawm.Process(name="align", script="scripts/align.sh")
p2.execute(depends_on=p1.hash)

p3 = jawm.Process(name="sort", script="scripts/sort.sh")
p3.execute(depends_on=p2.hash)
```

When `depends_on` is set, the Process waits for the upstream Process to finish before starting. If the upstream Process fails, the downstream Process is skipped (unless `always_run=True`).

You can also set `depends_on` as a list to wait on multiple upstream Processes:

```python
p3.execute(depends_on=[p1.hash, p2.hash])
```

---

### Writing the `test` sub-workflow

By convention, every module should expose a `test` sub-workflow — a lightweight sanity check that verifies the module is wired correctly without requiring real data or heavy computation.

A good `test` sub-workflow:

- Runs quickly (seconds, not minutes).
- Doesn't need real input data.
- Exercises the critical path: confirms scripts exist, containers can be pulled, and the Process finishes with exit code 0.
- Is gated behind `["main", "test"]` so it runs both standalone and as part of `main`.

```python
if jawm.utils.workflow(["main", "test"], workflows):
    jawm.Process(
        name="pipeline_test",
        script="""#!/bin/bash
set -euo pipefail
echo "Module test: checking environment"
which python3 || { echo "python3 not found"; exit 1; }
echo "All checks passed"
""",
        logs_directory="logs",
    ).execute()
```

Run it with:

```bash
python my_pipeline.py test
```

---

### Testing with `jawm-test`

For structured, repeatable testing with hash verification, jawm provides the `jawm-test` utility. It reads a `test/tests.txt` file, runs each defined workflow, and compares output hashes against stored references.

#### The tests file

`test/tests.txt` is a semicolon-separated file:

```
module;workflow;params;"name";hash
my_pipeline.py;main;yaml/docker.yaml;"Main workflow test";
```

Each row defines:

| Field | Description |
|---|---|
| `module` | The Python module file to run. |
| `workflow` | The sub-workflow name to invoke. |
| `params` | Parameter file(s) passed after `-p`. |
| `"name"` | A descriptive name for the test (quoted). |
| `hash` | The expected output hash. Leave empty on first run — `jawm-test` will fill it in. |

#### Running tests

```bash
cd jawm_my_pipeline

# Run tests and fill in hashes on first run
jawm-test

# Accept new hashes when outputs change intentionally
jawm-test --override

# Keep going even if a test fails
jawm-test --ignore
```

#### The downloads file

If your tests require input data, define a `test/data.txt` file:

```
d41d8cd98f00b204e9800998ecf8427e  sample.fastq.gz  https://example.com/data/sample.fastq.gz
```

Each line: `<md5> <filename> <url>`. `jawm-test` downloads, extracts (`.tar.gz`/`.tgz`), and verifies before running any tests.

#### Testing across environments

`jawm-test` can test against multiple Python versions and jawm versions:

```bash
# Test with Python 3.10 and 3.11 via pyenv
jawm-test -p 3.10.14 3.11.9

# Test with a specific jawm version from Git
jawm-test -j v2.0.0 --jawm_repo github.com/mpg-age-bioinformatics/jawm.git

# Test multiple module versions (tags/commits)
jawm-test -m current v1.0.0
```

---

### Inspecting variables with `jawm-dev lsvar`

When developing, it helps to see which `{{variables}}` your Process scripts reference. `jawm-dev lsvar` parses a module file and prints the variables as YAML:

```bash
jawm-dev lsvar my_pipeline.py
```

This scans every `jawm.Process(...)` block in the file, extracts `{{variable}}` references from the `script` blocks, and prints them grouped by process name. Useful for verifying that your YAML files define all the variables your scripts expect.

---

### Publishing your module

To share your module with others:

1. **Push to a Git repository** — use the `jawm_<name>` naming convention so the `jawm` CLI can find it by name.
2. **Tag releases** — use semver tags (e.g. `v1.0.0`) so consumers can pin to stable versions with `@v1.0.0` or use `@latest-tag`.
3. **Include `yaml/` defaults** — ship parameter YAML files for common configurations (Docker, Slurm, etc.) so consumers can get started with `jawm my_module -p yaml/docker.yaml`.
4. **Include `test/tests.txt`** — define at least one test so consumers (and CI) can verify the module works in their environment with `jawm-test`.
5. **Set up CI** — `jawm-dev init` scaffolds a `.github/workflows/test.yaml` that runs `jawm-test` on push. Enable it by uncommenting the trigger lines.

Once published, anyone can run your module directly:

```bash
jawm jawm_my_pipeline@v1.0.0 -p yaml/docker.yaml
```

Or load it into their own workflow:

```python
jawm.utils.load_modules(["jawm_my_pipeline@v1.0.0"])
```

---

### See Also

- [Module Overview](overview.md) — the concept and mental model behind modules.
- [Run a Module](run.md) — running modules from the command line.
- [Load Modules in Workflow](load.md) — composing modules in Python.
- [Utils → CLI Helpers](../utils.md#cli-helpers) — full reference for `parse_arguments()` and `workflow()`.
- [Process Overview](../process/overview.md) — the `Process` abstraction that modules build on.
- [YAML Config](../config/yaml.md) — the parameter file format.
